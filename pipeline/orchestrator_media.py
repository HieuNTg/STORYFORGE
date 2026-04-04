"""Media production: character reference images and scene images."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import ConfigManager
from services.seedream_client import SeedreamClient

logger = logging.getLogger(__name__)


class MediaProducer:
    """Handles media production: character images and scene images."""

    def __init__(self, config: ConfigManager):
        self.config = config

    def run(self, draft, enhanced, progress_callback=None) -> dict:
        """Generate character reference images and scene images.

        Returns dict with paths: {character_refs, scene_images}
        """
        result = {"character_refs": {}, "scene_images": []}
        cfg = self.config.pipeline

        def _log(msg):
            if progress_callback:
                progress_callback(msg)

        # Step 1: Character reference images (Seedream)
        seedream = SeedreamClient(api_key=cfg.seedream_api_key, base_url=cfg.seedream_api_url)
        if seedream.is_configured() and draft.characters:
            _log("[MEDIA] Tạo ảnh tham chiếu nhân vật...")
            for char in draft.characters:
                desc = char.appearance or char.personality or char.name
                ref_path = seedream.generate_character_reference(char.name, desc)
                if ref_path:
                    char.reference_image = ref_path
                    result["character_refs"][char.name] = ref_path
                    _log(f"[MEDIA] + {char.name}")

        # Step 1.5: Build/load enhanced character visual profiles
        visual_profiles = {}
        if cfg.enable_character_consistency and draft.characters:
            from services.character_visual_profile import CharacterVisualProfileStore
            from services.character_visual_extractor import CharacterVisualExtractor
            profile_store = CharacterVisualProfileStore()
            extractor = CharacterVisualExtractor()
            for char in draft.characters:
                profile = profile_store.load_profile(char.name)
                # Check if profile has frozen_prompt (enhanced profile)
                if not profile or not profile.get("frozen_prompt"):
                    _log(f"[MEDIA] Trích xuất visual profile: {char.name}...")
                    try:
                        attributes, frozen_prompt = extractor.extract_and_generate(char)
                        desc = profile_store.build_visual_description(char)
                        ref_path = result["character_refs"].get(char.name, "")
                        profile_store.save_enhanced_profile(
                            char.name, desc, attributes, frozen_prompt, ref_path
                        )
                        profile = profile_store.load_profile(char.name)
                    except Exception as e:
                        logger.warning("Visual extraction failed for %s: %s", char.name, e)
                        # Fallback: use simple text description
                        if not profile_store.has_profile(char.name):
                            desc = profile_store.build_visual_description(char)
                            ref_path = result["character_refs"].get(char.name, "")
                            profile_store.save_profile(char.name, desc, ref_path)
                        profile = profile_store.load_profile(char.name)

                if profile:
                    # Prefer frozen_prompt, fallback to description
                    visual_profiles[char.name] = profile.get("frozen_prompt") or profile.get("description", "")
                    if not char.reference_image and profile.get("reference_image"):
                        ref = profile["reference_image"]
                        if os.path.exists(ref):
                            char.reference_image = ref
                            result["character_refs"][char.name] = ref

        # Step 2: Scene images from enhanced story chapters (parallel)
        char_refs = result["character_refs"]
        use_consistency = cfg.enable_character_consistency

        if use_consistency:
            provider = getattr(cfg, "character_consistency_provider", "seedream")
            if provider == "seedream" and not seedream.is_configured():
                provider = cfg.image_provider
            from services.image_generator import ImageGenerator
            image_gen = ImageGenerator(provider=provider)
        else:
            image_gen = None

        if (use_consistency or seedream.is_configured()) and enhanced and enhanced.chapters:
            from services.image_prompt_generator import ImagePromptGenerator
            prompt_gen = ImagePromptGenerator()

            # Generate one scene image per chapter
            chapters = enhanced.chapters
            _log(f"[MEDIA] Tạo {len(chapters)} ảnh cảnh (song song)...")

            prepared = []
            for ch in chapters:
                try:
                    image_prompt = prompt_gen.generate_scene_prompt(ch)
                except Exception:
                    image_prompt = ch.summary or ch.title or f"Chapter {ch.chapter_number}"
                refs = list(char_refs.values())[:2]
                if use_consistency and visual_profiles:
                    # Use frozen English prompts directly (no longer Vietnamese descriptions)
                    char_descs = "; ".join(
                        f"[{n}: {visual_profiles[n]}]"
                        for n in visual_profiles
                        if n in [getattr(c, 'name', '') for c in (draft.characters or [])]
                    )
                    if char_descs:
                        image_prompt = f"{char_descs} {image_prompt}"
                filename = f"ch{ch.chapter_number:02d}_scene.png"
                prepared.append((ch, image_prompt, refs, filename))

            total = len(prepared)

            if use_consistency and image_gen is not None:
                # ImageGenerator path — use ThreadPoolExecutor directly
                max_workers = min(5, total)
                completed = 0
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(
                            image_gen.generate_with_reference if refs else image_gen.generate,
                            *(
                                (prompt, refs, filename)
                                if refs
                                else (prompt, filename)
                            ),
                        ): ch
                        for ch, prompt, refs, filename in prepared
                    }
                    for future in as_completed(futures):
                        ch = futures[future]
                        completed += 1
                        try:
                            path = future.result()
                            if path:
                                result["scene_images"].append(path)
                        except Exception as e:
                            logger.warning(
                                "Image gen failed for chapter %s: %s",
                                ch.chapter_number, e,
                            )
                        if completed % 3 == 0 or completed == total:
                            _log(f"[MEDIA] Ảnh: {completed}/{total}")
            else:
                # Seedream path — use batch_generate()
                batch_requests = [
                    {"scene_prompt": prompt, "reference_images": refs, "filename": filename}
                    for _ch, prompt, refs, filename in prepared
                ]
                batch_results = seedream.batch_generate(batch_requests)
                for i, img_result in enumerate(batch_results):
                    if img_result.success and img_result.image_url:
                        result["scene_images"].append(img_result.image_url)
                    else:
                        logger.warning(
                            "Image failed for %r: %s", img_result.prompt, img_result.error
                        )
                    completed_count = i + 1
                    if completed_count % 3 == 0 or completed_count == total:
                        _log(f"[MEDIA] Ảnh: {completed_count}/{total}")

        return result
