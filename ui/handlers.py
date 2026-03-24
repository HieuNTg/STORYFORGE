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
from services.tts_script_generator import TTSScriptGenerator
from services.share_manager import ShareManager
from services.user_manager import UserManager

logger = logging.getLogger(__name__)


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
        return f"Error: {e}", []


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
        return None, {"error": str(e)}


def handle_export_tts(orch_state, t) -> Optional[list]:
    """Export TTS script and return file list."""
    if orch_state is None:
        return None
    try:
        story = orch_state.output.enhanced_story or orch_state.output.story_draft
        if not story:
            return None
        gen = TTSScriptGenerator()
        script = gen.generate_full_script(story)
        path = gen.export_script(script, "output/tts_script.txt")
        return [path] if path else None
    except Exception as e:
        logger.error(f"TTS export error: {e}")
        return None


def handle_export_tts_audio(orch_state, voice: str = "female") -> tuple:
    """Export story as audio files using edge-tts. Returns (file_paths, status_msg)."""
    if orch_state is None:
        return None, "Chưa có truyện để xuất audio."
    try:
        from services.tts_audio_generator import TTSAudioGenerator

        story = orch_state.output.enhanced_story or orch_state.output.story_draft
        if not story or not story.chapters:
            return None, "Chưa có truyện để xuất audio."
        tts = TTSAudioGenerator(voice=voice)
        output_dir = os.path.join("output", "audiobook")
        paths = tts.generate_full_audiobook(story.chapters, output_dir)
        if paths:
            return paths, f"Đã tạo {len(paths)} file audio."
        return None, "Lỗi tạo audio."
    except Exception as e:
        logger.error(f"TTS audio export error: {e}")
        return None, f"Lỗi tạo audio: {e}"


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
        return f"Error: {e}", None


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


def handle_export_video_assets(orch_state, t) -> Optional[str]:
    """Export video assets ZIP and return path."""
    if orch_state is None:
        return None
    try:
        zip_path = orch_state.export_video_assets()
        return zip_path if zip_path else None
    except Exception as e:
        logger.error(f"Video asset export failed: {e}")
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


def handle_generate_images(orch_state, provider: str = "none", t=None) -> tuple:
    """Generate images from story video script panels.

    Returns (image_paths_list, status_msg).
    """
    if orch_state is None:
        msg = t("msg.no_story") if t else "No story loaded."
        return [], msg
    try:
        from services.image_generator import ImageGenerator
        from services.image_prompt_generator import ImagePromptGenerator

        video_script = orch_state.output.video_script if orch_state.output else None
        if not video_script or not video_script.panels:
            msg = t("info.no_video_script") if t else "No video script panels found."
            return [], msg

        prompt_gen = ImagePromptGenerator()
        image_gen = ImageGenerator(provider=provider)

        char_map: dict[str, str] = video_script.character_descriptions or {}
        image_prompts = [
            prompt_gen.generate_from_panel(panel, characters=char_map)
            for panel in video_script.panels
        ]

        # Group prompts by chapter for nicer filenames
        chapter_number = video_script.panels[0].chapter_number if video_script.panels else 0
        paths = image_gen.generate_story_images(image_prompts, chapter_number=chapter_number)

        msg = t("msg_images_generated") if t else f"Generated {len(paths)} image(s)."
        return paths, msg
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


def handle_compose_video(orch_state, voice: str = "female") -> tuple:
    """Generate TTS audio + compose video from storyboard panels.
    Returns (audio_files, video_file, status_msg).
    """
    if orch_state is None:
        return None, None, "Chưa có truyện."
    try:
        from services.tts_audio_generator import TTSAudioGenerator
        from services.video_composer import VideoComposer

        story = orch_state.output.enhanced_story or orch_state.output.story_draft
        video_script = orch_state.output.video_script if orch_state.output else None

        if not story or not story.chapters:
            return None, None, "Chưa có truyện để tạo video."

        # Step 1: TTS audio
        tts = TTSAudioGenerator(voice=voice)
        audio_dir = os.path.join("output", "audiobook")
        audio_paths = tts.generate_full_audiobook(story.chapters, audio_dir)

        # Step 2: Compose video if panels have images
        video_path = None
        if video_script and video_script.panels:
            has_images = any(
                getattr(p, "image_path", "") and os.path.exists(getattr(p, "image_path", ""))
                for p in video_script.panels
            )
            if has_images and audio_paths:
                composer = VideoComposer()
                merged_audio = composer.merge_chapter_audios(audio_paths)
                video_path = composer.compose(video_script.panels, merged_audio or "")

        status = f"✓ {len(audio_paths)} audio files"
        if video_path:
            status += f"\n✓ Video: {video_path}"
        else:
            status += "\n⚠️ Chưa có ảnh để ghép video (cần tạo ảnh trước)"

        return audio_paths or None, video_path, status
    except Exception as e:
        logger.error(f"Video compose error: {e}")
        return None, None, f"Lỗi: {e}"


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
            vs = getattr(output, "video_script", None)
            if vs:
                char_refs = getattr(vs, "character_refs", None)
        if not char_refs:
            return []
        return [(path, name) for name, path in char_refs.items() if path and os.path.exists(path)]
    except Exception as e:
        logger.error("Character gallery error: %s", e)
        return []
