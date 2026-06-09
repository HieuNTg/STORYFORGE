"""Extracted handler functions for the StoryForge Gradio UI.

These functions contain the business logic separated from the UI wiring in app.py.
They are called by Gradio event handlers defined in app.py.
"""

import logging
import os
from typing import Optional

from config import ConfigManager
from pipeline.orchestrator import PipelineOrchestrator
from services.pdf_exporter import PDFExporter
from services.share_manager import ShareManager
from services.user_manager import UserManager

logger = logging.getLogger(__name__)


# ── User-friendly error mapping ────────────────────────────────────────────────

_ERROR_MAP = [
    ("JSON validation", "error.json_validation"),
    ("json", "error.json_validation"),
    ("validation", "error.json_validation"),
    ("Connection", "error.api_connection"),
    ("connection", "error.api_connection"),
    ("ConnectionError", "error.api_connection"),
    ("Timeout", "error.timeout"),
    ("timeout", "error.timeout"),
    ("TimeoutError", "error.timeout"),
    ("APIError", "error.story_create_fail"),
    ("generation failed", "error.story_create_fail"),
    ("story", "error.story_create_fail"),
]


def _friendly_error(exc: Exception, t, fallback_key: str = "error.story_create_fail") -> str:
    """Map a technical exception to a user-friendly i18n message.

    Keeps the original detail in logs; returns a localised string for the UI.
    """
    exc_str = str(exc)
    exc_type = type(exc).__name__
    combined = f"{exc_type} {exc_str}"
    for needle, key in _ERROR_MAP:
        if needle in combined:
            return t(key)
    return t(fallback_key)


# ── Login / Register ──────────────────────────────────────────────────────────

def handle_login(username: str, password: str, t) -> tuple:
    """Authenticate user and return (profile_dict, status_msg, library_table)."""
    if not username or not password:
        return None, t("msg.login_fail"), []
    um = UserManager()
    profile = um.login(username, password)
    if profile:
        stories = um.list_stories(profile.user_id)
        table = [[s["story_id"], s["title"], s.get("saved_at", "")] for s in stories]
        return profile.model_dump(), f"{t('msg.login_success')} ({profile.username})", table
    return None, t("msg.login_fail"), []


def handle_register(username: str, password: str, t) -> tuple:
    """Register new user and return (profile_dict, status_msg, library_table)."""
    if not username or not password:
        return None, t("msg.register_fail"), []
    um = UserManager()
    try:
        profile = um.register(username, password)
        return profile.model_dump(), t("msg.register_success"), []
    except ValueError:
        return None, t("msg.register_fail"), []


def handle_save_story(user_state: Optional[dict], orch_state, title: str, t) -> tuple:
    """Save story to user library and return (status_msg, updated_table)."""
    if not user_state:
        return t("msg.no_login"), []
    if orch_state is None:
        return t("msg.no_story"), []
    um = UserManager()
    try:
        story_data = orch_state.output.model_dump() if orch_state.output else {}
        story_id = um.save_story(user_state["user_id"], story_data, title or "Untitled")
        um.track_usage(user_state["user_id"])
        stories = um.list_stories(user_state["user_id"])
        table = [[s["story_id"], s["title"], s.get("saved_at", "")] for s in stories]
        return f"{t('msg.story_saved')} ID: {story_id}", table
    except Exception as e:
        logger.error(f"Save story error: {e}")
        return _friendly_error(e, t, "error.save_fail"), []


# ── Export handlers ────────────────────────────────────────────────────────────

def handle_export_pdf(orch_state, t) -> tuple:
    """Export story as PDF and return (file_list, reading_stats_dict)."""
    if orch_state is None:
        return None, t("msg.no_story")
    try:
        story = orch_state.output.enhanced_story or orch_state.output.story_draft
        if not story:
            return None, t("msg.no_story")
        chars = orch_state.output.story_draft.characters if orch_state.output.story_draft else []
        path = PDFExporter.export(story, "output/story.pdf", characters=chars)
        stats = PDFExporter.compute_reading_stats(story).model_dump()
        return [path] if path else None, stats
    except Exception as e:
        logger.error(f"PDF export error: {e}")
        return None, {"error": _friendly_error(e, t, "error.export_fail")}


def handle_export_epub(orch_state, t) -> tuple:
    """Export story as EPUB and return (file_list, reading_stats_dict)."""
    if orch_state is None:
        return None, t("msg.no_story")
    try:
        from services.epub_exporter import EPUBExporter
        story = orch_state.output.enhanced_story or orch_state.output.story_draft
        if not story:
            return None, t("msg.no_story")
        chars = orch_state.output.story_draft.characters if orch_state.output.story_draft else []
        path = EPUBExporter.export(story, "output/story.epub", characters=chars)
        stats = PDFExporter.compute_reading_stats(story).model_dump()
        return [path] if path else None, stats
    except Exception as e:
        logger.error(f"EPUB export error: {e}")
        return None, {"error": _friendly_error(e, t, "error.export_fail")}


def handle_share_story(orch_state, t) -> tuple:
    """Create shareable HTML link and return (link, None)."""
    if orch_state is None:
        return "", t("msg.no_story")
    try:
        story = orch_state.output.enhanced_story or orch_state.output.story_draft
        if not story:
            return "", t("msg.no_story")
        chars = orch_state.output.story_draft.characters if orch_state.output.story_draft else []
        mgr = ShareManager()
        share = mgr.create_share(story, characters=chars)
        base = ConfigManager().pipeline.share_base_url or "file://"
        link = f"{base}{share.html_path}"
        return link, None
    except Exception as e:
        logger.error(f"Share error: {e}")
        return _friendly_error(e, t, "error.export_fail"), None


# ── File export helpers ────────────────────────────────────────────────────────

def handle_export_files(orch_state, formats) -> Optional[list]:
    """Export story files in given formats and return file paths."""
    if orch_state is None:
        return None
    try:
        paths = orch_state.export_output(formats=formats)
        return paths if paths else None
    except Exception as e:
        logger.error(f"Export failed: {e}")
        return None


def handle_export_zip(orch_state, formats, t) -> Optional[list]:
    """Export story as ZIP and return file list."""
    if orch_state is None:
        return None
    try:
        zip_path = orch_state.export_zip(formats=formats)
        return [zip_path] if zip_path else None
    except Exception as e:
        logger.error(f"ZIP export failed: {e}")
        return None




# ── Checkpoint helpers ─────────────────────────────────────────────────────────

def get_checkpoint_choices() -> list[str]:
    """List available checkpoints formatted for Dropdown."""
    ckpts = PipelineOrchestrator.list_checkpoints()
    return [f"{c['file']} ({c['modified']}, {c['size_kb']}KB)" for c in ckpts]


def resolve_checkpoint_path(ckpt_choice: str) -> Optional[str]:
    """Extract filesystem path from dropdown choice string."""
    if not ckpt_choice:
        return None
    filename = ckpt_choice.split(" (")[0]
    return os.path.join(PipelineOrchestrator.CHECKPOINT_DIR, filename)


# ── Continuation helpers ───────────────────────────────────────────────────────

def handle_load_checkpoint(ckpt_choice: str, orch, t) -> tuple:
    """Load checkpoint into orchestrator and return (summary, orch)."""
    path = resolve_checkpoint_path(ckpt_choice)
    if not path:
        return t("continue.no_checkpoint"), orch
    if orch is None:
        orch = PipelineOrchestrator()
    orch.load_from_checkpoint(path)
    d = orch.output.story_draft
    if d:
        summary = t("continue.loaded", title=d.title, chapters=len(d.chapters))
        summary += f"\n{d.synopsis[:200]}..." if d.synopsis else ""
        chars = ", ".join(c.name for c in d.characters[:8])
        summary += f"\n{t('format.characters_label', names=chars)}"
        return summary, orch
    return t("continue.no_story"), orch


def handle_add_chapters(orch, n_chapters: int, w_count: int, t) -> tuple:
    """Add chapters to existing story and return (log, orch)."""
    if orch is None or not orch.output.story_draft:
        return t("continue.no_story"), orch
    logs = []
    orch.continue_story(
        additional_chapters=int(n_chapters),
        word_count=int(w_count),
        progress_callback=lambda m: logs.append(m),
    )
    return "\n".join(logs) + "\n" + t("continue.chapters_added", count=int(n_chapters)), orch


def handle_delete_chapters(orch, from_ch: int, t) -> tuple:
    """Delete chapters from given number and return (log, orch)."""
    if orch is None or not orch.output.story_draft:
        return t("continue.no_story"), orch
    orch.remove_chapters(int(from_ch))
    return t("continue.chapters_deleted", from_ch=int(from_ch)), orch


def handle_update_character(orch, name: str, personality: str, motivation: str, t) -> tuple:
    """Update character attributes and return (log, orch)."""
    if orch is None or not orch.output.story_draft:
        return t("continue.no_story"), orch
    if not name:
        return t("continue.char_name"), orch
    updates = {}
    if personality:
        updates["personality"] = personality
    if motivation:
        updates["motivation"] = motivation
    if not updates:
        return t("continue.char_personality") + " / " + t("continue.char_motivation"), orch
    orch.update_character(name, updates)
    return t("continue.char_updated", name=name), orch


def handle_generate_images(orch_state, provider: str = "none", t=None, chapter_number: int | None = None) -> tuple:
    """Generate one image per chapter, persist filenames onto chapter.images.

    If ``chapter_number`` is provided, only that single chapter is regenerated
    (other chapters are left untouched). Returns (image_paths_list, status_msg).
    Paths are basenames relative to the /media static mount.
    """
    if orch_state is None:
        msg = t("msg.no_story") if t else "No story loaded."
        return [], msg
    try:
        story = orch_state.output.enhanced_story or orch_state.output.story_draft if orch_state.output else None
        if not story or not story.chapters:
            msg = t("msg.no_story") if t else "No story loaded."
            return [], msg

        from services.image_generator import ImageGenerator
        from services.image_prompt_generator import ImagePromptGenerator

        draft = orch_state.output.story_draft if orch_state.output else None
        characters = list(getattr(draft, "characters", []) or []) if draft else []

        visual_profiles: dict[str, str] = {}
        character_references: dict[str, str] = {}
        try:
            from services.character_visual_profile import CharacterVisualProfileStore
            store = CharacterVisualProfileStore(story_title=getattr(draft, "title", None))
            missing = []
            for c in characters:
                fp = store.get_frozen_prompt(c.name)
                if fp:
                    visual_profiles[c.name] = fp
                else:
                    missing.append(c)
                ref = store.get_reference_image(c.name)
                if ref:
                    character_references[c.name] = ref
            # Auto-build for checkpoint-loaded stories that never went through MediaProducer.
            if missing:
                logger.info(
                    "Auto-building visual profiles for %d character(s) on first image regen",
                    len(missing),
                )
                from services.character_visual_extractor import CharacterVisualExtractor
                extractor = CharacterVisualExtractor()
                for c in missing:
                    try:
                        attributes, frozen_prompt = extractor.extract_and_generate(c)
                        desc = store.build_visual_description(c)
                        store.save_enhanced_profile(c.name, desc, attributes, frozen_prompt, "")
                        visual_profiles[c.name] = frozen_prompt
                    except Exception as e:
                        logger.warning("Auto-build visual profile failed for %s: %s", c.name, e)
        except Exception as _vp_e:
            logger.debug("Visual profile lookup skipped: %s", _vp_e)

        prompt_gen = ImagePromptGenerator()
        _story_title = getattr(draft, "title", None) if draft else None
        _session_id = getattr(orch_state, "session_id", None)
        image_gen = ImageGenerator(
            provider=provider,
            session_id=_session_id,
            story_title=_story_title,
        )

        if chapter_number is not None:
            target_chapters = [c for c in story.chapters if c.chapter_number == chapter_number]
            if not target_chapters:
                msg = f"Chapter {chapter_number} not found."
                return [], msg
        else:
            target_chapters = list(story.chapters)

        from config import ConfigManager
        _pipeline_cfg = ConfigManager().pipeline
        # Per-chapter panel count. With ``panels_auto`` on, each chapter is paneled
        # to its OWN length — a long chapter gets more panels, a short one fewer —
        # so the comic breathes with the prose instead of forcing a rigid count
        # onto every chapter. Bounded by panels_min..panels_max at roughly one
        # panel per ``words_per_panel`` words; with it off, every chapter uses the
        # fixed ``panels_per_chapter``. The SAME count feeds both the base-prompt
        # extractor and the shot-list stage so they stay zip-aligned (see
        # apply_shot_list_to_prompts).
        _panels_fixed = max(1, int(getattr(_pipeline_cfg, "panels_per_chapter", 8)))
        _panels_auto = bool(getattr(_pipeline_cfg, "panels_auto", True))
        _panels_min = max(1, int(getattr(_pipeline_cfg, "panels_min", 4)))
        _panels_max = max(_panels_min, int(getattr(_pipeline_cfg, "panels_max", 12)))
        _words_per_panel = max(1, int(getattr(_pipeline_cfg, "words_per_panel", 200)))

        def _panels_for(chapter) -> int:
            if not _panels_auto:
                return _panels_fixed
            words = len((getattr(chapter, "content", "") or "").split())
            return max(_panels_min, min(_panels_max, round(words / _words_per_panel)))
        # Comic Phase 2: Beat→Shot-list stage. Gated dark by default so it can be
        # A/B'd and rolled back safely; image generation is unchanged when off.
        _shot_list_enabled = bool(getattr(_pipeline_cfg, "comic_shot_list_enabled", False))
        _shot_extractor = None
        if _shot_list_enabled:
            try:
                from services.shot_list import ShotListExtractor
                _shot_extractor = ShotListExtractor()
            except Exception as _sl_e:
                logger.warning("Shot-list stage unavailable, skipping: %s", _sl_e)
                _shot_extractor = None

        # Comic Phase 3: Page Compositor. Only meaningful when the shot-list stage
        # is also on (it consumes the shot-list's bubbles/captions/screen_side).
        # When both are enabled, the clean panels are composited into finished comic
        # PAGE PNGs which then REPLACE the loose panels in ``ch.images`` (and the
        # returned paths) so the frontend reader surfaces pages with no contract
        # change. Loose panels stay on disk alongside. Gated dark; any failure
        # degrades to loose panels.
        _compositor_enabled = bool(getattr(_pipeline_cfg, "comic_compositor_enabled", False))

        # Provider branch: Codex/ChatGPT renders in-image Vietnamese text well,
        # so for that provider we bake the speech bubbles + dialogue INTO each
        # panel (and skip the vector-bubble compositor below). FlowKit and the
        # other providers keep clean text-free panels + the compositor overlay.
        _is_codex = str(provider or "").strip().lower() == "codex"

        # Comic: extract character → MAKE a character reference image → feed it
        # into panel generation, so faces/outfits stay consistent across panels.
        # The text profiles were built above; here we render ONE clean portrait
        # per character from its frozen prompt and link it onto both the profile
        # store (durable cache) and ``character_references`` (consumed per panel by
        # generate_story_images). Gated to comic mode + reference-capable providers
        # and idempotent — characters that already have a usable reference on disk
        # are skipped, so this costs one portrait/character only on the first run.
        _REF_CAPABLE = {"flowkit", "codex", "seedream", "replicate"}
        if _shot_list_enabled and provider in _REF_CAPABLE and characters:
            import re as _re
            _portrait_store = None
            try:
                from services.character_visual_profile import CharacterVisualProfileStore
                _portrait_store = CharacterVisualProfileStore(story_title=_story_title)
            except Exception as _ps_e:
                logger.debug("Portrait store unavailable: %s", _ps_e)
            try:
                os.makedirs(os.path.join(image_gen.output_dir, "avatars"), exist_ok=True)
            except Exception:
                pass
            _made = 0
            for c in characters:
                if character_references.get(c.name):
                    continue  # already conditioned on an existing reference image
                fp = visual_profiles.get(c.name)
                if not fp and _portrait_store is not None:
                    fp = _portrait_store.get_frozen_prompt(c.name)
                if not fp:
                    continue  # no visual profile to render a portrait from
                _safe = _re.sub(r"[^\w\-]+", "_", c.name).strip("_") or "character"
                portrait_prompt = (
                    f"{fp}\n\nCharacter reference portrait: a single full-color "
                    f"portrait of THIS ONE character only, head-and-shoulders, front "
                    f"three-quarter view, neutral expression, even soft lighting, "
                    f"plain flat studio background, the whole face clearly visible. "
                    f"No other characters. Do not draw any speech bubbles, captions, "
                    f"signs, sound-effects, labels, or written words of any kind, in "
                    f"any language — keep the image completely free of lettering."
                )
                try:
                    _ref_path = image_gen.generate(
                        portrait_prompt,
                        filename=os.path.join("avatars", f"{_safe}.png"),
                    )
                except Exception as _ge:
                    logger.warning("Character portrait gen failed for %s: %s", c.name, _ge)
                    _ref_path = None
                if _ref_path and os.path.exists(_ref_path):
                    character_references[c.name] = _ref_path
                    _made += 1
                    if _portrait_store is not None:
                        try:
                            _portrait_store.set_reference_image(c.name, _ref_path)
                        except Exception:
                            pass
            if _made or character_references:
                logger.info(
                    "Comic: %d character reference portrait(s) ready (%d total refs)",
                    _made, len(character_references),
                )

        all_paths: list[str] = []
        for ch in target_chapters:
            num_panels = _panels_for(ch)
            prompts = prompt_gen.generate_from_chapter(
                ch,
                characters=characters or None,
                num_images=num_panels,
                visual_profiles=visual_profiles or None,
            )
            if not prompts:
                continue
            _chapter_shot_list = None  # populated below when the shot-list stage runs
            # Beat→Shot-list: runs between chapter prose and image generation.
            # The shot-list is persisted onto ``ch.shot_list`` (carried alongside
            # the panels for Phase 3's compositor) and its panel metadata
            # (shot_type/dialogue/screen_side) is threaded onto the ImagePrompts.
            # Image prompt TEXT stays text-free (FlowKit) — dialogue is
            # compositor-only — UNLESS the provider is Codex, which bakes the
            # bubbles into the panel itself (see the _is_codex branch below).
            if _shot_extractor is not None:
                try:
                    from services.shot_list import apply_shot_list_to_prompts
                    shot_list = _shot_extractor.extract(
                        ch,
                        characters=characters or None,
                        num_panels=num_panels,
                        character_references=character_references or None,
                        visual_profiles=visual_profiles or None,
                    )
                    if shot_list.pages:
                        apply_shot_list_to_prompts(prompts, shot_list)
                        ch.shot_list = shot_list.model_dump()
                        _chapter_shot_list = shot_list
                        if _is_codex:
                            # Codex draws the bubbles itself — rewrite the prompts
                            # to bake in this panel's dialogue (verbatim VN text)
                            # instead of the clean text-free panel FlowKit uses.
                            from services.image_prompt_generator import (
                                bake_dialogue_into_prompts,
                            )
                            bake_dialogue_into_prompts(prompts)
                except Exception as _sl_e:
                    logger.warning(
                        "Shot-list extraction failed for ch %s, continuing without: %s",
                        ch.chapter_number, _sl_e,
                    )
            ch_paths = image_gen.generate_story_images(
                prompts,
                chapter_number=ch.chapter_number,
                character_references=character_references or None,
            )
            # Comic Phase 3: composite the clean loose panels into finished comic
            # PAGE PNGs and surface THOSE through ch.images / the returned paths.
            # Loose panels remain on disk (ch_paths above); only what the chapter
            # *exposes* changes. Any failure degrades silently to loose panels.
            if (
                _compositor_enabled
                and _shot_list_enabled
                and _chapter_shot_list is not None
                and ch_paths
                and not _is_codex  # codex panels already carry baked-in bubbles
            ):
                try:
                    from services.media.page_compositor import compose_chapter, PageGeometry
                    import os as _os
                    _pages_dir = _os.path.join(image_gen.output_dir, "pages")
                    _geom = PageGeometry.from_canvas_spec(
                        getattr(_pipeline_cfg, "comic_page_canvas", None)
                    )
                    _font = getattr(_pipeline_cfg, "comic_font", None) or None
                    _mode = getattr(_pipeline_cfg, "comic_layout_mode", "shot_list")
                    page_paths = compose_chapter(
                        _chapter_shot_list,
                        ch_paths,
                        _pages_dir,
                        chapter_number=ch.chapter_number,
                        geometry=_geom,
                        font_path=_font,
                        layout_mode=_mode,
                    )
                    if page_paths:
                        ch_paths = page_paths
                except Exception as _comp_e:
                    logger.warning(
                        "Page compositor failed for ch %s, using loose panels: %s",
                        ch.chapter_number, _comp_e,
                    )
            # Store paths relative to the output root so the ``/media`` mount
            # (which serves OUTPUT_ROOT) resolves them as ``/media/<rel>``.
            # Panels live at ``output/<story-slug>/images/...`` under the
            # per-story layout.
            from services.output_paths import rel_to_output_root
            ch.images = [rel_to_output_root(p) for p in ch_paths]
            all_paths.extend(ch_paths)

        msg = t("msg_images_generated") if t else f"Generated {len(all_paths)} image(s)."
        return all_paths, msg
    except Exception as e:
        logger.error("Image generation error: %s", e)
        msg = f"Error: {e}"
        return [], msg


def handle_enhance(orch, n_sim: int, w_count: int, t) -> tuple:
    """Re-run enhancement layer and return (log, orch)."""
    if orch is None or not orch.output.story_draft:
        return t("continue.no_story"), orch
    logs = []
    orch.enhance_chapters(
        num_sim_rounds=int(n_sim),
        word_count=int(w_count),
        progress_callback=lambda m: logs.append(m),
    )
    return "\n".join(logs) + "\n" + t("continue.enhanced"), orch


# ── Genre presets ──────────────────────────────────────────────────────────────

GENRE_PRESETS = {
    "Tiên Hiệp": {"num_chapters": 50, "words_per_chapter": 3000, "writing_style": "Miêu tả chi tiết"},
    "Huyền Huyễn": {"num_chapters": 40, "words_per_chapter": 3000, "writing_style": "Miêu tả chi tiết"},
    "Ngôn Tình": {"num_chapters": 30, "words_per_chapter": 2500, "writing_style": "Trữ tình lãng mạn"},
    "Cung Đấu": {"num_chapters": 40, "words_per_chapter": 2800, "writing_style": "Miêu tả chi tiết"},
    "Đô Thị": {"num_chapters": 30, "words_per_chapter": 2500, "writing_style": "Đối thoại sắc bén"},
    "Kiếm Hiệp": {"num_chapters": 40, "words_per_chapter": 3000, "writing_style": "Miêu tả chi tiết"},
    "Xuyên Không": {"num_chapters": 40, "words_per_chapter": 2800, "writing_style": "Miêu tả chi tiết"},
    "Trọng Sinh": {"num_chapters": 40, "words_per_chapter": 2800, "writing_style": "Miêu tả chi tiết"},
}


def handle_genre_autofill(genre_value: str) -> tuple:
    """Return preset (num_chapters, words_per_chapter, writing_style) for genre."""
    preset = GENRE_PRESETS.get(genre_value)
    if not preset:
        return (None, None, None)
    return (preset["num_chapters"], preset["words_per_chapter"], preset["writing_style"])


# ── Character gallery handler ──────────────────────────────────────────────────

def handle_export_wattpad(orch_state, t) -> tuple:
    """Export story in Wattpad-ready format. Returns (zip_file_list, metadata_dict)."""
    if orch_state is None:
        return None, {"error": "No story"}
    story = orch_state.output.enhanced_story or orch_state.output.story_draft
    if not story:
        return None, {"error": "No story data"}
    try:
        from services.wattpad_exporter import PlatformExporter
        result = PlatformExporter.export_wattpad(story)
        zip_path = result.get("zip_path")
        return [zip_path] if zip_path else result["files"], result["metadata"]
    except Exception as e:
        logger.error(f"Wattpad export failed: {e}")
        return None, {"error": str(e)}


def handle_character_gallery(orch_state) -> list:
    """Populate character gallery from pipeline output. Returns list of (path, name)."""
    if orch_state is None:
        return []
    try:
        output = getattr(orch_state, "output", None)
        if not output:
            return []
        char_refs = getattr(output, "character_refs", None)
        if not char_refs:
            return []
        return [(path, name) for name, path in char_refs.items() if path and os.path.exists(path)]
    except Exception as e:
        logger.error("Character gallery error: %s", e)
        return []
