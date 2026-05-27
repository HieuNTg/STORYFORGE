"""Media production: character reference images and scene images."""

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import ConfigManager
from services.media.image_provider import ImageProvider
from services.safe_name import safe_character_name

logger = logging.getLogger(__name__)


def _mentions(name: str, blob: str) -> bool:
    """Word-boundary check for a character name inside a text blob.

    Substring `name in blob` falsely matches Vietnamese single-syllable names:
    "An" hits "Anh", "Vũ" hits "Vũ khí". That misroutes refs and anchors the
    wrong character into the scene prompt. Anchor with `\\w` boundaries instead.
    """
    if not name:
        return False
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", blob) is not None


class MediaProducer:
    """Handles media production: character images and scene images."""

    def __init__(self, config: ConfigManager):
        self.config = config

    def run(self, draft, enhanced, progress_callback=None, session_id: str | None = None) -> dict:
        """Generate character reference images and scene images.

        Returns dict with paths: {character_refs, scene_images}
        """
        result = {"character_refs": {}, "scene_images": []}
        cfg = self.config.pipeline

        def _log(msg):
            if progress_callback:
                progress_callback(msg)

        # Step 1: Character reference images.
        #
        # Order of preference per character:
        #   1) extract-endpoint avatar already on disk (output/images/avatars/)
        #      — this lets the user shape characters via the Forge UI, generate
        #      avatars there, and have those exact images be the consistency
        #      anchor for every chapter / comic panel downstream.
        #   2) Seedream-generated reference (legacy path, only if configured).
        #
        # We intentionally do NOT regenerate when an avatar exists — it would
        # break visual continuity across chapters.
        from services.character_avatar import find_existing_avatar

        provider = ImageProvider()
        provider.seedream.api_key = cfg.seedream_api_key or provider.seedream.api_key
        provider.seedream.base_url = cfg.seedream_api_url or provider.seedream.base_url

        # Story scope for avatar lookup. The orchestrator runs against a
        # specific story so we pass that id through to find_existing_avatar
        # — that way a chapter from "Story A" can't accidentally pick up an
        # avatar that was generated for a same-named character in "Story B".
        #
        # StoryDraft has no id/story_id field in the schema; session_id is
        # the canonical story scope in StoryForge (session-per-story model,
        # threaded down from orchestrator_layers.run_full_pipeline). When the
        # orchestrator runs without a session (CLI / standalone tests), fall
        # back to a title-derived slug so cross-story isolation still holds.
        # Falls back to legacy unscoped lookup automatically when both None.
        story_id = session_id or (
            safe_character_name(getattr(draft, "title", "") or "")
            if getattr(draft, "title", None)
            else None
        )

        if draft.characters:
            _log("[MEDIA] Tạo ảnh tham chiếu nhân vật...")
            for char in draft.characters:
                existing = find_existing_avatar(char.name, story_id=story_id)
                if existing:
                    char.reference_image = existing
                    result["character_refs"][char.name] = existing
                    _log(f"[MEDIA] = {char.name} (avatar có sẵn)")
                    continue
                if provider.is_configured():
                    desc = char.appearance or char.personality or char.name
                    ref_path = provider.generate_character_reference(char.name, desc)
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
            consistency_provider = getattr(cfg, "character_consistency_provider", "seedream")
            if consistency_provider == "seedream" and not provider.is_configured():
                consistency_provider = cfg.image_provider
            from services.image_generator import ImageGenerator
            image_gen = ImageGenerator(
                provider=consistency_provider,
                session_id=session_id,
                story_title=getattr(draft, "title", None),
            )
        else:
            image_gen = None

        if (use_consistency or provider.is_configured()) and enhanced and enhanced.chapters:
            from services.image_prompt_generator import ImagePromptGenerator
            prompt_gen = ImagePromptGenerator()

            # Generate one scene image per chapter
            chapters = enhanced.chapters
            _log(f"[MEDIA] Tạo {len(chapters)} ảnh cảnh (song song)...")

            # Scene-aware ref selection. Detect which characters actually
            # appear in this chapter's content/summary/title via substring
            # match against the character name, then prefer those refs over
            # arbitrary dict-insertion order. The image model only accepts
            # 2 refs total (FlowKit limit) so picking the wrong two means
            # the antagonist's face leaks into a chapter that's purely about
            # the protagonist.
            def _refs_for_chapter(ch) -> list[str]:
                if not char_refs:
                    return []
                blob = " ".join(
                    s for s in (
                        getattr(ch, "content", "") or "",
                        getattr(ch, "summary", "") or "",
                        getattr(ch, "title", "") or "",
                    ) if s
                )
                # Order matches `char_refs` (draft.characters order), so
                # protagonists tend to come first when ties happen — that's
                # the right default vs. random.
                mentioned = [
                    n for n, _ref in char_refs.items() if _mentions(n, blob)
                ]
                picked_names = mentioned[:2] if mentioned else list(char_refs.keys())[:2]
                return [char_refs[n] for n in picked_names if n in char_refs]

            prepared = []
            for ch in chapters:
                try:
                    image_prompt = prompt_gen.generate_scene_prompt(ch)
                except Exception:
                    image_prompt = ch.summary or ch.title or f"Chapter {ch.chapter_number}"
                refs = _refs_for_chapter(ch)
                if use_consistency and visual_profiles:
                    # When we have image refs to feed FlowKit, the frozen
                    # English visual description fights the reference image
                    # (the text prompt re-describes hair/skin/outfit which
                    # the ref already pins down) and produces drift. With
                    # refs, only inject the bare name so the model knows
                    # *who* is in the scene and lets the image ref dominate
                    # appearance. Without refs, fall back to the full frozen
                    # description so the model still has appearance anchors.
                    # Also: scope the injected names to characters who actually
                    # appear in this chapter (heuristic-driven via the same
                    # substring match used for refs), so we don't tell the
                    # model "[Hắc Phong Lão Tổ]" is in a chapter where only
                    # the protagonist appears.
                    chapter_blob = " ".join(
                        s for s in (
                            getattr(ch, "content", "") or "",
                            getattr(ch, "summary", "") or "",
                            getattr(ch, "title", "") or "",
                        ) if s
                    )
                    valid_names = [
                        n for n in visual_profiles
                        if n in [getattr(c, 'name', '') for c in (draft.characters or [])]
                    ]
                    scene_names = [n for n in valid_names if _mentions(n, chapter_blob)]
                    if not scene_names:
                        scene_names = valid_names  # fallback: anchor everyone
                    if refs:
                        char_descs = "; ".join(f"[{n}]" for n in scene_names)
                    else:
                        char_descs = "; ".join(
                            f"[{n}: {visual_profiles[n]}]" for n in scene_names
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
                # Seedream path — use batch_generate() via ImageProvider
                batch_requests = [
                    {"scene_prompt": prompt, "reference_images": refs, "filename": filename}
                    for _ch, prompt, refs, filename in prepared
                ]
                batch_results = provider.seedream.batch_generate(batch_requests)
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
