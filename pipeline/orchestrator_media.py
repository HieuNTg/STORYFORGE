"""Media production: character reference images and scene images."""

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import ConfigManager
from services.media.image_provider import ImageProvider
from services.safe_name import safe_character_name

logger = logging.getLogger(__name__)


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
            # Scope profiles by story TITLE only (not session) so the read side
            # — which addresses a story by checkpoint/session that may differ
            # from the writing session — resolves to the same folder. Title is
            # the one identity stable across runs of the same story.
            profile_store = CharacterVisualProfileStore(
                story_title=getattr(draft, "title", None)
            )
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

        # Step 2: Comic panels (truyện tranh) — multiple images per chapter.
        #
        # Each chapter gets ``panels_per_chapter`` distinct scene panels. We
        # reuse the same engine as the on-demand reader regen
        # (ImagePromptGenerator.generate_from_chapter + ImageGenerator.
        # generate_story_images) so the pipeline and the regen button stay in
        # lockstep. generate_from_chapter already injects ``visual_profiles``
        # into the per-character description block (consistency anchors), and
        # generate_story_images routes each panel's ``characters_in_scene``
        # through the matching character reference image for img2img-capable
        # providers. The generated panel paths are written onto ``ch.images``
        # (relative to OUTPUT_ROOT) — the same chapter objects live in
        # ``self.output.enhanced_story``, so the caller persists them by
        # checkpointing after this stage.
        char_refs = result["character_refs"]
        use_consistency = cfg.enable_character_consistency

        # Resolve which provider actually generates panels. With consistency on
        # we prefer the dedicated consistency provider, falling back to the
        # generic image provider when seedream isn't configured.
        if use_consistency:
            panel_provider = getattr(cfg, "character_consistency_provider", "seedream")
            if panel_provider == "seedream" and not provider.is_configured():
                panel_provider = cfg.image_provider
        else:
            panel_provider = cfg.image_provider

        if panel_provider and panel_provider != "none" and enhanced and enhanced.chapters:
            from services.image_generator import ImageGenerator
            from services.image_prompt_generator import ImagePromptGenerator
            from services.output_paths import rel_to_output_root

            num_panels = max(1, int(getattr(cfg, "panels_per_chapter", 8)))
            prompt_gen = ImagePromptGenerator()
            image_gen = ImageGenerator(
                provider=panel_provider,
                session_id=session_id,
                story_title=getattr(draft, "title", None),
            )
            characters = list(getattr(draft, "characters", None) or [])

            chapters = enhanced.chapters
            total = len(chapters)
            _log(f"[MEDIA] Tạo {num_panels} panel/chương cho {total} chương...")

            def _panels_for_chapter(ch):
                """Generate this chapter's panels; returns (ch, [rel_paths])."""
                try:
                    prompts = prompt_gen.generate_from_chapter(
                        ch,
                        characters=characters or None,
                        num_images=num_panels,
                        visual_profiles=visual_profiles or None,
                    )
                except Exception as e:
                    logger.warning(
                        "Panel prompt generation failed for chapter %s: %s",
                        ch.chapter_number, e,
                    )
                    return ch, []
                if not prompts:
                    return ch, []
                paths = image_gen.generate_story_images(
                    prompts,
                    chapter_number=ch.chapter_number,
                    character_references=char_refs or None,
                )
                return ch, [rel_to_output_root(p) for p in paths]

            # Parallelize across chapters (panels within a chapter run
            # sequentially inside generate_story_images). Cap workers so we
            # don't hammer the image provider with total*num_panels at once.
            completed = 0
            with ThreadPoolExecutor(max_workers=min(4, total)) as executor:
                futures = {executor.submit(_panels_for_chapter, ch): ch for ch in chapters}
                for future in as_completed(futures):
                    completed += 1
                    ch = futures[future]
                    try:
                        ch_obj, rel_paths = future.result()
                        if rel_paths:
                            ch_obj.images = rel_paths
                            result["scene_images"].extend(rel_paths)
                    except Exception as e:
                        logger.warning(
                            "Panel generation failed for chapter %s: %s",
                            getattr(ch, "chapter_number", "?"), e,
                        )
                    _log(f"[MEDIA] Chương: {completed}/{total}")

        return result
