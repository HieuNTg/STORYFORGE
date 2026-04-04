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

        # Step 1.5: Build/load character visual profiles if consistency enabled
        visual_profiles = {}
        if cfg.enable_character_consistency and draft.characters:
            from services.character_visual_profile import CharacterVisualProfileStore
            profile_store = CharacterVisualProfileStore()
            for char in draft.characters:
                if not profile_store.has_profile(char.name):
                    desc = profile_store.build_visual_description(char)
                    ref_path = result["character_refs"].get(char.name, "")
                    profile_store.save_profile(char.name, desc, ref_path)
                profile = profile_store.load_profile(char.name)
                if profile:
                    visual_profiles[char.name] = profile.get("description", "")
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
                    char_descs = "; ".join(
                        f"[{n}: {visual_profiles[n]}]"
                        for n in visual_profiles
                    )
                    if char_descs:
                        image_prompt = f"{char_descs} {image_prompt}"
                filename = f"ch{ch.chapter_number:02d}_scene.png"
                prepared.append((ch, image_prompt, refs, filename))

            completed = 0
            total = len(prepared)
            max_workers = min(5, total)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                if use_consistency and image_gen is not None:
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
                else:
                    futures = {
                        executor.submit(seedream.generate_scene, prompt, refs, filename): ch
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
                        logger.warning(f"Image gen failed for chapter {ch.chapter_number}: {e}")
                    if completed % 3 == 0 or completed == total:
                        _log(f"[MEDIA] Ảnh: {completed}/{total}")

        return result
