"""Gradio UI builder for StoryForge — extracted from app.py.

Exports:
    create_ui() -> gr.Blocks
"""

import html as _html
import json
import logging
import threading
import queue
import os
import time
import unicodedata
import gradio as gr
from fastapi.responses import JSONResponse

from config import ConfigManager
from pipeline.orchestrator import PipelineOrchestrator
from services.i18n import I18n
from services.image_prompt_generator import ImagePromptGenerator
from ui.handlers import (
    handle_export_files, handle_export_zip, handle_export_video_assets,
    get_checkpoint_choices,
    handle_load_checkpoint, handle_add_chapters, handle_delete_chapters,
    handle_update_character, handle_enhance, handle_generate_images,
    handle_genre_autofill, handle_character_gallery,
)
from ui.tabs import (
    build_pipeline_tab,
    build_story_tab,
    build_simulation_tab,
    build_video_tab,
    build_review_tab,
    build_export_tab,
    build_settings_tab,
    build_analytics_tab,
    build_reader_tab,
)
from ui.tabs.branching_tab import build_branching_tab
from ui.tabs.onboarding_tab import build_onboarding_banner

logger = logging.getLogger(__name__)

# i18n singleton — initialized with saved language preference
i18n = I18n()
_saved_lang = ConfigManager().pipeline.language
if _saved_lang and _saved_lang != i18n.lang:
    i18n.set_language(_saved_lang)

# Genre/style/drama keys for locale lookup
_GENRE_KEYS = [
    "genre.tien_hiep", "genre.huyen_huyen", "genre.kiem_hiep", "genre.do_thi",
    "genre.ngon_tinh", "genre.xuyen_khong", "genre.trong_sinh", "genre.he_thong",
    "genre.khoa_huyen", "genre.dong_nhan", "genre.lich_su", "genre.quan_su",
    "genre.linh_di", "genre.trinh_tham", "genre.hai_huoc", "genre.vong_du",
    "genre.di_gioi", "genre.mat_the", "genre.dien_van", "genre.cung_dau",
]

_STYLE_KEYS = [
    "style.descriptive", "style.dialogue", "style.action",
    "style.romance", "style.dark",
]

_DRAMA_KEYS = ["drama.low", "drama.medium", "drama.high"]


def _t(key: str, **kwargs) -> str:
    """Shortcut for i18n.t()."""
    return i18n.t(key, **kwargs)


def _status_badge(css_class: str, key: str) -> str:
    """Generate HTML status badge with escaped locale text."""
    return f'<span class="status-badge {css_class}">{_html.escape(_t(key))}</span>'


def _genres() -> list[str]:
    return [_t(k) for k in _GENRE_KEYS]


def _styles() -> list[str]:
    return [_t(k) for k in _STYLE_KEYS]


def _drama_levels() -> list[str]:
    return [_t(k) for k in _DRAMA_KEYS]


# Template path
TEMPLATES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "templates", "story_templates.json",
)


def _load_templates() -> dict:
    """Load story templates from JSON file."""
    if os.path.exists(TEMPLATES_PATH):
        try:
            with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load templates from {TEMPLATES_PATH}: {e}")
    return {}


def _progress_html(layer: int = 0, step: str = "") -> str:
    """Generate progress bar HTML. layer: 0=idle, 1/2/3/4=active layer."""
    segments = []
    icons = ["1", "2", "3", "4"]
    labels = [_t("progress.layer1"), _t("progress.layer2"), _t("progress.layer3"), "Media"]
    for i in range(4):
        lnum = i + 1
        if layer > lnum:
            cls = "progress-segment done"
        elif layer == lnum:
            cls = "progress-segment active"
        else:
            cls = "progress-segment"
        segments.append(
            f'<div class="{cls}">'
            f'<span style="font-size:10px;opacity:0.7;margin-right:4px">{icons[i]}</span>'
            f'{labels[i]}</div>'
        )
    bar = f'<div class="progress-bar-container">{"".join(segments)}</div>'
    step_div = f'<div class="progress-step-text">{_html.escape(step)}</div>' if step else ""
    return bar + step_div


def _strip_diacritics(text: str) -> str:
    """Remove Vietnamese diacritics for robust matching."""
    nfkd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def _detect_layer(msg: str) -> int:
    """Detect current layer from progress log message."""
    normalized = _strip_diacritics(msg).upper()
    if "MEDIA" in normalized or "IMAGE" in normalized or "TTS" in normalized or "AUDIO" in normalized:
        return 4
    if "LAYER 3" in normalized or "STORYBOARD" in normalized or "VIDEO" in normalized:
        return 3
    if "LAYER 2" in normalized or "MO PHONG" in normalized or "ENHANCE" in normalized:
        return 2
    if "LAYER 1" in normalized or "TAO TRUYEN" in normalized or "CHUONG" in normalized:
        return 1
    return 0


_APP_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,
    secondary_hue=gr.themes.colors.slate,
    neutral_hue=gr.themes.colors.gray,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
    font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
).set(
    body_background_fill="linear-gradient(135deg, #f5f7fa 0%, #e8ecf4 100%)",
    block_background_fill="white",
    block_border_width="0px",
    block_shadow="0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06)",
    block_radius="12px",
    button_primary_background_fill="linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
    button_primary_text_color="white",
    button_primary_shadow="0 4px 14px rgba(79,70,229,0.35)",
    button_secondary_background_fill="white",
    button_secondary_border_color="#e0e0e0",
    button_secondary_shadow="0 1px 3px rgba(0,0,0,0.06)",
    input_background_fill="#fafbfc",
    input_border_color="#e2e8f0",
    input_radius="8px",
    checkbox_background_color="#f0f0ff",
    checkbox_border_color="#c7d2fe",
)
_APP_CSS = """
/* ── Global ── */
.gradio-container { max-width: 1400px !important; margin: 0 auto !important; }

/* ── Header ── */
.pipeline-header {
    text-align: center; margin-bottom: 8px; padding: 20px 0 10px;
}
.pipeline-header h1 {
    background: linear-gradient(135deg, #4f46e5, #7c3aed);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    font-size: 2rem !important; font-weight: 800 !important; letter-spacing: -0.02em;
}
.pipeline-header h3 {
    color: #64748b !important; font-weight: 400 !important;
    font-size: 1rem !important; margin-top: 4px !important;
}

/* ── Tab navigation ── */
.tabs > .tab-nav {
    background: white; border-radius: 12px; padding: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 16px;
    gap: 2px !important;
}
.tabs > .tab-nav button {
    border-radius: 8px !important; font-weight: 600 !important;
    padding: 10px 20px !important; transition: all 0.2s ease !important;
    border: none !important; font-size: 13px !important;
}
.tabs > .tab-nav button.selected {
    background: linear-gradient(135deg, #4f46e5, #6366f1) !important;
    color: white !important; box-shadow: 0 2px 8px rgba(79,70,229,0.3) !important;
}
.tabs > .tab-nav button:not(.selected):hover {
    background: #f1f5f9 !important;
}

/* ── Card sections ── */
.layer-box {
    border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;
    margin: 12px 0; background: white;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}

/* ── Progress stepper ── */
.progress-bar-container {
    display: flex; gap: 0; margin: 12px 0; height: 44px;
    background: #f1f5f9; border-radius: 12px; overflow: hidden;
    box-shadow: inset 0 1px 3px rgba(0,0,0,0.06);
}
.progress-segment {
    flex: 1; display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 600; color: #94a3b8;
    transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    background: transparent; position: relative;
}
.progress-segment.active {
    background: linear-gradient(135deg, #4f46e5, #6366f1);
    color: white; animation: pulse-glow 2s infinite;
    box-shadow: 0 0 20px rgba(79,70,229,0.3);
}
.progress-segment.done {
    background: linear-gradient(135deg, #059669, #10b981);
    color: white;
}
.progress-segment.done::after {
    content: " ✓"; font-size: 11px;
}
@keyframes pulse-glow {
    0%, 100% { opacity: 1; box-shadow: 0 0 20px rgba(79,70,229,0.3); }
    50% { opacity: 0.85; box-shadow: 0 0 30px rgba(79,70,229,0.5); }
}
.progress-step-text {
    text-align: center; font-size: 13px; color: #64748b;
    margin: 6px 0 10px 0; min-height: 20px; font-weight: 500;
}

/* ── Status badge ── */
.status-badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 16px; border-radius: 20px;
    font-size: 13px; font-weight: 600;
}
.status-idle { background: #f1f5f9; color: #64748b; }
.status-running {
    background: linear-gradient(135deg, #dbeafe, #e0e7ff);
    color: #4338ca; animation: pulse-glow 2s infinite;
}
.status-done {
    background: linear-gradient(135deg, #dcfce7, #d1fae5);
    color: #059669;
}
.status-error {
    background: linear-gradient(135deg, #fee2e2, #fecaca);
    color: #dc2626;
}

/* ── Buttons ── */
.gr-button-primary {
    transition: all 0.2s ease !important;
}
.gr-button-primary:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 20px rgba(79,70,229,0.4) !important;
}
.gr-button-secondary:hover {
    border-color: #6366f1 !important; color: #4f46e5 !important;
}
button.lg {
    padding: 12px 24px !important; font-size: 15px !important;
    font-weight: 700 !important; border-radius: 10px !important;
}

/* ── Accordion ── */
.gr-accordion { border-radius: 10px !important; border: 1px solid #e2e8f0 !important; }
.gr-accordion .label-wrap { padding: 12px 16px !important; }

/* ── Inputs ── */
.gr-input, .gr-text-input textarea, .gr-dropdown {
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}
.gr-input:focus, .gr-text-input textarea:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.15) !important;
}

/* ── Form section headers ── */
.form-section-header {
    font-size: 14px !important; font-weight: 700 !important;
    color: #334155 !important; margin: 16px 0 8px !important;
    padding-bottom: 6px; border-bottom: 2px solid #e2e8f0;
}

/* ── Onboarding banner ── */
.onboarding-banner {
    background: linear-gradient(135deg, #eef2ff, #e0e7ff) !important;
    border: 1px solid #c7d2fe !important;
    border-radius: 12px !important; padding: 16px 20px !important;
}

/* ── Output panels ── */
.output-panel textarea {
    font-family: 'Inter', system-ui, sans-serif !important;
    line-height: 1.7 !important;
}

/* ── Mobile responsive ── */
@media (max-width: 768px) {
    .gr-row { flex-direction: column !important; }
    .gr-column { min-width: 100% !important; }
    .progress-segment { font-size: 10px; }
    .gradio-button { min-height: 44px; }
    .tabs > .tab-nav { flex-wrap: wrap; }
    .tabs > .tab-nav button { flex: 1 1 45%; font-size: 11px !important; padding: 8px 12px !important; }
    .pipeline-header h1 { font-size: 1.5rem !important; }
}
@media (max-width: 480px) {
    .tabs > .tab-nav button { flex: 1 1 100%; }
    .gradio-container { padding: 8px !important; }
}

/* ── Compact mode ── */
.compact-mode .prose { font-size: 14px; }
.compact-mode .block { padding: 8px !important; }
.compact-mode .tabs > .tab-nav button { padding: 6px 12px !important; font-size: 11px !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

/* ── Animation for new content ── */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
.tabitem { animation: fadeIn 0.3s ease; }
"""

# Uptime reference shared with health endpoint inside create_ui
_START_TIME: float = 0.0


def set_start_time(t: float) -> None:
    """Set uptime reference from app.py at startup."""
    global _START_TIME
    _START_TIME = t


def create_ui():
    """Tạo giao diện Gradio."""

    with gr.Blocks(
        title="StoryForge",
    ) as app:
        build_onboarding_banner(_t)

        gr.Markdown(
            f"# {_t('app.title')}\n### {_t('app.subtitle')}",
            elem_classes="pipeline-header",
        )

        with gr.Tabs():
            # ═══════════════════════════════════════
            # TAB 1: PIPELINE ĐẦY ĐỦ
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.pipeline")):
                with gr.Row():
                    with gr.Column(scale=1):
                        form = build_pipeline_tab(_t, _genres, _styles, _drama_levels)
                        genre_input = form["genre_input"]
                        template_dropdown = form["template_dropdown"]
                        quick_start_btn = form["quick_start_btn"]
                        title_input = form["title_input"]
                        style_input = form["style_input"]
                        idea_input = form["idea_input"]
                        num_chapters = form["num_chapters"]
                        num_characters = form["num_characters"]
                        word_count = form["word_count"]
                        sim_rounds = form["sim_rounds"]
                        drama_level = form["drama_level"]
                        shots_per_ch = form["shots_per_ch"]
                        enable_agents_cb = form["enable_agents_cb"]
                        enable_scoring_cb = form["enable_scoring_cb"]
                        enable_media_cb = form["enable_media_cb"]
                        run_btn = form["run_btn"]

                    with gr.Column(scale=2):
                        # Status + Progress bar
                        status_html = gr.HTML(
                            value=_status_badge("status-idle", "status.ready"),
                        )
                        progress_bar = gr.HTML(value=_progress_html(0))

                        # Live preview
                        live_preview = gr.Textbox(
                            label=_t("label.live_preview"),
                            lines=8, interactive=False,
                        )

                        # Collapsed detail log
                        with gr.Accordion(_t("accordion.detail"), open=False):
                            progress_log = gr.Textbox(
                                label=_t("label.log"), lines=8, interactive=False,
                            )

                        # Output tabs
                        with gr.Tabs():
                            with gr.TabItem(_t("tab.story")):
                                story = build_story_tab(_t)
                                draft_output = story["draft_output"]
                                enhanced_output = story["enhanced_output"]
                            with gr.TabItem(_t("tab.simulation")):
                                sim = build_simulation_tab(_t)
                                sim_output = sim["sim_output"]
                                escalation_display = sim["escalation_display"]
                            with gr.TabItem(_t("tab.video")):
                                vid = build_video_tab(_t)
                                video_output = vid["video_output"]
                                video_export_btn = vid["video_export_btn"]
                                video_export_file = vid["video_export_file"]
                                image_prompts_df = vid["image_prompts_df"]
                                image_provider_dd = vid["image_provider_dd"]
                                generate_images_btn = vid["generate_images_btn"]
                                image_gallery = vid["image_gallery"]
                                tts_voice_dd = vid["tts_voice_dd"]
                                generate_tts_btn = vid["generate_tts_btn"]
                                compose_video_btn = vid["compose_video_btn"]
                                tts_audio_output = vid["tts_audio_output"]
                                video_output_file = vid["video_output_file"]
                                video_status = vid["video_status"]
                                character_gallery = vid["character_gallery"]
                            with gr.TabItem(_t("tab.review")):
                                rev = build_review_tab(_t)
                                agent_output = rev["agent_output"]
                                quality_output = rev["quality_output"]

                        export_formats = gr.CheckboxGroup(
                            choices=["TXT", "Markdown", "JSON", "HTML"],
                            value=["TXT", "Markdown", "JSON", "HTML"],
                            label=_t("label.export_format"),
                        )
                        with gr.Row():
                            export_btn = gr.Button(_t("btn.export"))
                            zip_btn = gr.Button(_t("btn.download_zip"))
                        export_files_output = gr.File(
                            label=_t("label.file_output"), file_count="multiple",
                        )

                        gr.Markdown(_t("section.checkpoint"))
                        with gr.Row():
                            checkpoint_dropdown = gr.Dropdown(
                                label=_t("label.resume_checkpoint"),
                                choices=[], interactive=True,
                            )
                            refresh_ckpt_btn = gr.Button(_t("btn.refresh"), scale=0)
                        resume_btn = gr.Button(_t("btn.resume"), variant="secondary")

                        # ── Story Continuation ──
                        with gr.Accordion(_t("continue.title"), open=False):
                            continue_summary = gr.Textbox(
                                label=_t("continue.story_summary"),
                                lines=3, interactive=False,
                                value=_t("continue.no_story"),
                            )
                            load_ckpt_btn = gr.Button(
                                _t("btn.refresh") + " + Load", variant="secondary",
                            )

                            with gr.Row():
                                continue_chapters = gr.Slider(
                                    1, 20, value=3, step=1,
                                    label=_t("continue.num_chapters"),
                                )
                                continue_btn = gr.Button(
                                    _t("continue.btn_add"), variant="primary",
                                )

                            with gr.Row():
                                delete_from_ch = gr.Slider(
                                    1, 50, value=1, step=1,
                                    label=_t("continue.delete_from"),
                                )
                                delete_btn = gr.Button(
                                    _t("continue.btn_delete"), variant="stop",
                                )

                            enhance_btn = gr.Button(
                                _t("continue.btn_enhance"), variant="secondary",
                            )

                            gr.Markdown(_t("continue.char_editor"))
                            with gr.Row():
                                char_name_input = gr.Textbox(
                                    label=_t("continue.char_name"), scale=1,
                                )
                                char_personality_input = gr.Textbox(
                                    label=_t("continue.char_personality"), scale=2,
                                )
                                char_motivation_input = gr.Textbox(
                                    label=_t("continue.char_motivation"), scale=2,
                                )
                            update_char_btn = gr.Button(
                                _t("continue.btn_update_char"), variant="secondary",
                            )

                            continue_log = gr.Textbox(
                                label=_t("continue.log"), lines=5, interactive=False,
                            )

                # Shared orchestrator state
                orchestrator_state = gr.State(None)
                user_state = gr.State(None)

                # ── Output formatter ──
                def _format_output(output, logs, orch):
                    """Format PipelineOutput for UI display. Returns 13-tuple."""
                    draft_text = ""
                    if output and output.story_draft:
                        d = output.story_draft
                        draft_text = f"# {d.title}\n\n"
                        draft_text += _t("format.genre_label", genre=d.genre) + "\n"
                        draft_text += _t("format.synopsis_label", synopsis=d.synopsis) + "\n\n"
                        draft_text += _t("format.characters_label", names=', '.join(c.name for c in d.characters)) + "\n\n"
                        for ch in d.chapters:
                            draft_text += f"\n---\n## {_t('format.chapter', number=ch.chapter_number, title=ch.title)}\n\n"
                            draft_text += ch.content[:2000] + "...\n"

                    sim_text = ""
                    if output and output.simulation_result:
                        s = output.simulation_result
                        sim_text = _t("sim.title") + "\n\n"
                        sim_text += _t("sim.events_count", count=len(s.events)) + "\n"
                        sim_text += _t("sim.posts_count", count=len(s.agent_posts)) + "\n\n"
                        sim_text += _t("sim.events_header") + "\n"
                        for e in s.events[:10]:
                            sim_text += (
                                f"- [{e.event_type}] {e.description} "
                                f"({_t('quality.drama').lower()}: {e.drama_score:.1f})\n"
                            )
                        sim_text += "\n" + _t("sim.suggestions_header") + "\n"
                        for sug in s.drama_suggestions[:5]:
                            sim_text += f"- {sug}\n"

                    enhanced_text = ""
                    if output and output.enhanced_story:
                        es = output.enhanced_story
                        enhanced_text = f"# {es.title} {_t('format.drama_version')}\n"
                        enhanced_text += _t("format.drama_score", score=f"{es.drama_score:.2f}") + "\n\n"
                        for ch in es.chapters:
                            enhanced_text += f"\n---\n## {_t('format.chapter', number=ch.chapter_number, title=ch.title)}\n\n"
                            enhanced_text += ch.content[:2000] + "...\n"

                    video_text = ""
                    if output and output.video_script:
                        vs = output.video_script
                        video_text = _t("format.video_title", title=vs.title) + "\n"
                        video_text += _t("format.video_duration", minutes=f"{vs.total_duration_seconds/60:.1f}") + "\n"
                        video_text += _t("format.video_panels", count=len(vs.panels)) + "\n"
                        video_text += _t("format.video_voicelines", count=len(vs.voice_lines)) + "\n\n"
                        for p in vs.panels[:20]:
                            video_text += (
                                f"### Panel {p.panel_number} (Ch.{p.chapter_number})\n"
                                f"- {_t('format.shot_label', shot=p.shot_type.value, camera=p.camera_movement)}\n"
                                f"- {_t('format.description_label', desc=p.description)}\n"
                            )
                            if p.dialogue:
                                video_text += f"- {_t('format.dialogue_label', text=p.dialogue)}\n"
                            if p.image_prompt:
                                video_text += f"- {_t('format.image_prompt_label', prompt=p.image_prompt)}\n"
                            video_text += "\n"

                    agent_text = ""
                    if output and output.reviews:
                        agent_text = _t("review.title") + "\n\n"
                        for r in output.reviews:
                            status = "PASS" if r.approved else "FAIL"
                            agent_text += f"### {r.agent_name} (Layer {r.layer}, Round {r.iteration})\n"
                            agent_text += f"- {_t('review.score', score=f'{r.score:.1f}', status=status)}\n"
                            if r.issues:
                                agent_text += f"- {_t('review.issues', text='; '.join(r.issues[:3]))}\n"
                            if r.suggestions:
                                agent_text += f"- {_t('review.suggestions', text='; '.join(r.suggestions[:3]))}\n"
                            agent_text += "\n"

                    quality_text = ""
                    if output and output.quality_scores:
                        quality_text = _t("quality.title") + "\n\n"
                        for qs in output.quality_scores:
                            quality_text += f"### Layer {qs.scoring_layer} — {_t('quality.total', score=f'{qs.overall:.1f}')}\n\n"
                            quality_text += (
                                f"| {'Metric'} | {'Score'} |\n|---|---|\n"
                                f"| {_t('quality.coherence')} | {qs.avg_coherence:.1f} |\n"
                                f"| {_t('quality.character')} | {qs.avg_character:.1f} |\n"
                                f"| {_t('quality.drama')} | {qs.avg_drama:.1f} |\n"
                                f"| {_t('quality.writing')} | {qs.avg_writing:.1f} |\n\n"
                            )
                            quality_text += _t("quality.weakest", chapter=qs.weakest_chapter) + "\n\n"
                            coh = _t('quality.coherence')
                            char = _t('quality.character')
                            dra = _t('quality.drama')
                            wri = _t('quality.writing')
                            quality_text += f"| Ch. | {coh} | {char} | {dra} | {wri} | Total | Notes |\n"
                            quality_text += "|---|---|---|---|---|---|---|\n"
                            for cs in qs.chapter_scores:
                                quality_text += (
                                    f"| {cs.chapter_number} | {cs.coherence:.1f} | "
                                    f"{cs.character_consistency:.1f} | {cs.drama:.1f} | "
                                    f"{cs.writing_quality:.1f} | {cs.overall:.1f} | "
                                    f"{cs.notes[:50]} |\n"
                                )
                            quality_text += "\n---\n\n"

                        if len(output.quality_scores) >= 2:
                            l1 = output.quality_scores[0].overall
                            l2 = output.quality_scores[1].overall
                            diff = l2 - l1
                            sign = "+" if diff > 0 else ""
                            quality_text += _t("quality.improvement", sign=sign, diff=f"{diff:.1f}") + "\n"

                    # Build image prompts table from video script panels
                    image_prompts_rows = []
                    if output and output.video_script:
                        img_gen = ImagePromptGenerator()
                        chars_map = {}
                        if output.story_draft:
                            chars_map = {c.name: c.appearance or c.personality for c in output.story_draft.characters}
                        for panel in output.video_script.panels:
                            ip = img_gen.generate_from_panel(panel, chars_map)
                            image_prompts_rows.append([
                                f"Ch.{ip.chapter_number} P.{ip.panel_number}",
                                ip.dalle_prompt,
                                ip.sd_prompt,
                            ])

                    # Build escalation events from simulation result (high drama_score)
                    escalation_data = None
                    if output and output.simulation_result:
                        high_drama = [
                            {
                                "event_type": e.event_type,
                                "description": e.description,
                                "drama_score": round(e.drama_score, 2),
                                "characters": e.characters_involved,
                            }
                            for e in output.simulation_result.events
                            if e.drama_score >= 0.7
                        ]
                        if high_drama:
                            escalation_data = high_drama

                    run_status = "done" if output else "error"
                    status_label = _t("status.done") if output else _t("status.error")
                    return (
                        f'<span class="status-badge status-{run_status}">{_html.escape(status_label)}</span>',
                        _progress_html(4 if output else 0, _t("status.complete_label") if output else ""),
                        "",  # clear live preview
                        "\n".join(output.logs if output else logs),
                        draft_text, sim_text, enhanced_text, video_text, agent_text,
                        quality_text or _t("output.no_quality_alt"), orch,
                        image_prompts_rows or None, escalation_data,
                    )

                # ── Pipeline runner ──
                def run_pipeline(
                    title, genre, style, idea, n_chapters, n_chars,
                    w_count, n_sim, _drama, n_shots, agents_enabled,
                    scoring_enabled, media_enabled, user_state_data=None,
                ):
                    # Strip inputs before validation
                    title = (title or "").strip()
                    idea = (idea or "").strip()
                    errors = []
                    if len(title) > 200:
                        errors.append("Tiêu đề không được vượt quá 200 ký tự.")
                    if not idea or len(idea) < 10:
                        errors.append(_t("error.idea_too_short"))
                    elif len(idea) > 10000:
                        errors.append("Ý tưởng không được vượt quá 10.000 ký tự.")
                    if n_chapters < 1 or n_chapters > 50:
                        errors.append(_t("error.chapter_range"))
                    if errors:
                        yield (
                            _status_badge("status-error", "status.error"),
                            _progress_html(0),
                            "", "\n".join(errors), "", "", "", "", "", "", None, None, None,
                        )
                        return

                    # ── Credit check (logged-in users only) ──
                    if user_state_data:
                        try:
                            from models.schemas import UserProfile
                            from services.credit_manager import CreditManager
                            profile = UserProfile(**user_state_data)
                            cm = CreditManager()
                            allowed, msg = cm.check_credits(profile, "story_generation")
                            if not allowed:
                                yield (
                                    _status_badge("status-error", "status.error"),
                                    _progress_html(0),
                                    "", msg, "", "", "", "", "", "", None, None, None,
                                )
                                return
                            cm.deduct_credits(profile, "story_generation")
                        except (ImportError, AttributeError, TypeError, ValueError, OSError) as e:
                            logger.warning(f"Credit check skipped due to error: {e}")

                    orch = PipelineOrchestrator()
                    logs = []
                    progress_queue = queue.Queue()
                    stream_text = [""]

                    def on_progress(msg):
                        logs.append(msg)
                        progress_queue.put(("log", msg))

                    last_stream_time = [0.0]

                    def on_stream(partial_text):
                        stream_text[0] = partial_text
                        now = time.time()
                        if now - last_stream_time[0] > 0.2:
                            progress_queue.put(("stream", partial_text))
                            last_stream_time[0] = now

                    result = [None]

                    def _run():
                        result[0] = orch.run_full_pipeline(
                            title=title or f"{_t('tab.story')} {genre}",
                            genre=genre,
                            idea=idea,
                            style=style,
                            num_chapters=int(n_chapters),
                            num_characters=int(n_chars),
                            word_count=int(w_count),
                            num_sim_rounds=int(n_sim),
                            shots_per_chapter=int(n_shots),
                            progress_callback=on_progress,
                            stream_callback=on_stream,
                            enable_agents=agents_enabled,
                            enable_scoring=scoring_enabled,
                            enable_media=media_enabled,
                        )

                    thread = threading.Thread(target=_run)
                    thread.start()

                    current_preview = ""
                    while thread.is_alive():
                        try:
                            msg_type, msg_data = progress_queue.get(timeout=0.1)
                            while not progress_queue.empty():
                                try:
                                    t, d = progress_queue.get_nowait()
                                    if t == "stream":
                                        msg_type, msg_data = t, d
                                except queue.Empty:
                                    break
                            if msg_type == "stream":
                                current_preview = msg_data
                            layer = _detect_layer(logs[-1]) if logs else 0
                            yield (
                                _status_badge("status-running", "status.running"),
                                _progress_html(layer, logs[-1] if logs else ""),
                                current_preview, "\n".join(logs),
                                "", "", "", "", "", "", None, None, None,
                            )
                        except queue.Empty:
                            continue

                    thread.join()

                    if stream_text[0]:
                        layer = _detect_layer(logs[-1]) if logs else 0
                        yield (
                            _status_badge("status-running", "status.running"),
                            _progress_html(layer, logs[-1] if logs else ""),
                            stream_text[0], "\n".join(logs),
                            "", "", "", "", "", "", None, None, None,
                        )

                    output = result[0]
                    yield _format_output(output, logs, orch)

                # Pipeline outputs list (reused by run + quick_start + resume)
                _pipeline_outputs = [
                    status_html, progress_bar, live_preview, progress_log,
                    draft_output, sim_output, enhanced_output, video_output,
                    agent_output, quality_output, orchestrator_state,
                    image_prompts_df, escalation_display,
                ]
                _pipeline_inputs = [
                    title_input, genre_input, style_input, idea_input,
                    num_chapters, num_characters, word_count,
                    sim_rounds, drama_level, shots_per_ch, enable_agents_cb,
                    enable_scoring_cb, enable_media_cb, user_state,
                ]

                run_btn.click(
                    fn=run_pipeline,
                    inputs=_pipeline_inputs,
                    outputs=[
                        status_html, progress_bar, live_preview, progress_log,
                        draft_output, sim_output, enhanced_output, video_output,
                        agent_output, quality_output, orchestrator_state,
                        image_prompts_df, escalation_display,
                    ],
                )
                quick_start_btn.click(fn=run_pipeline, inputs=_pipeline_inputs, outputs=_pipeline_outputs)

                # ── Template handlers ──
                templates_data = _load_templates()

                def update_template_choices(genre):
                    genre_templates = templates_data.get(genre, [])
                    choices = [t["title"] for t in genre_templates]
                    return gr.update(choices=choices, value=choices[0] if choices else None)

                def apply_template(genre, template_title):
                    genre_templates = templates_data.get(genre, [])
                    for t in genre_templates:
                        if t["title"] == template_title:
                            return (
                                t["title"],
                                t.get("style", "Miêu tả chi tiết"),
                                t["idea"],
                                t.get("num_chapters", 5),
                                t.get("num_characters", 5),
                                t.get("words_per_chapter", 1500),
                            )
                    return (gr.update(), gr.update(), gr.update(),
                            gr.update(), gr.update(), gr.update())

                def genre_autofill(genre_value):
                    n_ch, w_ch, style = handle_genre_autofill(genre_value)
                    return (
                        gr.update(value=n_ch) if n_ch else gr.update(),
                        gr.update(value=w_ch) if w_ch else gr.update(),
                        gr.update(value=style) if style else gr.update(),
                    )

                genre_input.change(
                    fn=update_template_choices,
                    inputs=[genre_input],
                    outputs=[template_dropdown],
                )
                genre_input.change(
                    fn=genre_autofill,
                    inputs=[genre_input],
                    outputs=[num_chapters, word_count, style_input],
                )
                template_dropdown.change(
                    fn=apply_template,
                    inputs=[genre_input, template_dropdown],
                    outputs=[title_input, style_input, idea_input,
                             num_chapters, num_characters, word_count],
                )
                app.load(fn=update_template_choices, inputs=[genre_input], outputs=[template_dropdown])

                # ── Export handlers ──
                def export_files(orch, formats):
                    return handle_export_files(orch, formats)

                def export_zip_handler(orch, formats):
                    return handle_export_zip(orch, formats, _t)

                export_btn.click(
                    fn=export_files,
                    inputs=[orchestrator_state, export_formats],
                    outputs=[export_files_output],
                )
                zip_btn.click(
                    fn=export_zip_handler,
                    inputs=[orchestrator_state, export_formats],
                    outputs=[export_files_output],
                )

                def export_video_assets(orch):
                    if orch is None:
                        gr.Info(_t("info.run_pipeline_first"))
                        return None
                    result = handle_export_video_assets(orch, _t)
                    if result is None:
                        gr.Info(_t("info.no_video_script"))
                    return result

                video_export_btn.click(
                    fn=export_video_assets,
                    inputs=[orchestrator_state],
                    outputs=[video_export_file],
                )

                # ── Image generation handler ──
                def generate_images_and_refresh(orch, provider):
                    paths, msg = handle_generate_images(orch, provider, t=_t)
                    if msg:
                        gr.Info(msg)
                    gallery = handle_character_gallery(orch)
                    return paths or [], gallery

                generate_images_btn.click(
                    fn=generate_images_and_refresh,
                    inputs=[orchestrator_state, image_provider_dd],
                    outputs=[image_gallery, character_gallery],
                )

                # ── TTS Audio handler ──
                def tts_audio_handler(orch, voice):
                    from ui.handlers import handle_export_tts_audio
                    paths, msg = handle_export_tts_audio(orch, voice)
                    if msg:
                        gr.Info(msg)
                    return paths or []

                generate_tts_btn.click(
                    fn=tts_audio_handler,
                    inputs=[orchestrator_state, tts_voice_dd],
                    outputs=[tts_audio_output],
                )

                # ── Video compose handler ──
                def compose_video_handler(orch, voice):
                    from ui.handlers import handle_compose_video
                    audio_files, video_file, status = handle_compose_video(orch, voice)
                    return audio_files or [], video_file, status

                compose_video_btn.click(
                    fn=compose_video_handler,
                    inputs=[orchestrator_state, tts_voice_dd],
                    outputs=[tts_audio_output, video_output_file, video_status],
                )

                # ── Checkpoint handlers ──
                def refresh_checkpoints():
                    choices = get_checkpoint_choices()
                    return gr.update(choices=choices, value=choices[0] if choices else None)

                refresh_ckpt_btn.click(fn=refresh_checkpoints, outputs=[checkpoint_dropdown])

                def resume_pipeline(ckpt_choice, n_sim, n_shots, w_count, agents_enabled):
                    if not ckpt_choice:
                        yield (
                            _status_badge("status-error", "status.error"),
                            _progress_html(0),
                            "", _t("error.select_checkpoint"), "", "", "", "", "", "", None, None, None,
                        )
                        return

                    filename = ckpt_choice.split(" (")[0]
                    ckpt_path = os.path.join(PipelineOrchestrator.CHECKPOINT_DIR, filename)

                    orch = PipelineOrchestrator()
                    logs = []
                    progress_q = queue.Queue()
                    stream_text = [""]

                    def on_progress(msg):
                        logs.append(msg)
                        progress_q.put(("log", msg))

                    last_stream_time = [0.0]

                    def on_stream(partial_text):
                        stream_text[0] = partial_text
                        now = time.time()
                        if now - last_stream_time[0] > 0.2:
                            progress_q.put(("stream", partial_text))
                            last_stream_time[0] = now

                    result = [None]

                    def _run():
                        result[0] = orch.resume_from_checkpoint(
                            ckpt_path,
                            progress_callback=on_progress,
                            stream_callback=on_stream,
                            enable_agents=agents_enabled,
                            num_sim_rounds=int(n_sim),
                            shots_per_chapter=int(n_shots),
                            word_count=int(w_count),
                        )

                    thread = threading.Thread(target=_run)
                    thread.start()

                    current_preview = ""
                    while thread.is_alive():
                        try:
                            msg_type, msg_data = progress_q.get(timeout=0.1)
                            while not progress_q.empty():
                                try:
                                    t, d = progress_q.get_nowait()
                                    if t == "stream":
                                        msg_type, msg_data = t, d
                                except queue.Empty:
                                    break
                            if msg_type == "stream":
                                current_preview = msg_data
                            layer = _detect_layer(logs[-1]) if logs else 0
                            yield (
                                _status_badge("status-running", "status.running"),
                                _progress_html(layer, logs[-1] if logs else ""),
                                current_preview, "\n".join(logs),
                                "", "", "", "", "", "", None, None, None,
                            )
                        except queue.Empty:
                            continue

                    thread.join()

                    if stream_text[0]:
                        layer = _detect_layer(logs[-1]) if logs else 0
                        yield (
                            _status_badge("status-running", "status.running"),
                            _progress_html(layer, logs[-1] if logs else ""),
                            stream_text[0], "\n".join(logs),
                            "", "", "", "", "", "", None, None, None,
                        )

                    output = result[0]
                    yield _format_output(output, logs, orch)

                resume_btn.click(
                    fn=resume_pipeline,
                    inputs=[checkpoint_dropdown, sim_rounds, shots_per_ch, word_count, enable_agents_cb],
                    outputs=_pipeline_outputs,
                )

                # ── Continuation handlers ──
                def load_checkpoint_for_continuation(ckpt_choice, orch):
                    return handle_load_checkpoint(ckpt_choice, orch, _t)

                load_ckpt_btn.click(
                    fn=load_checkpoint_for_continuation,
                    inputs=[checkpoint_dropdown, orchestrator_state],
                    outputs=[continue_summary, orchestrator_state],
                )

                def add_chapters_handler(orch, n_chapters, w_count):
                    return handle_add_chapters(orch, n_chapters, w_count, _t)

                continue_btn.click(
                    fn=add_chapters_handler,
                    inputs=[orchestrator_state, continue_chapters, word_count],
                    outputs=[continue_log, orchestrator_state],
                )

                def delete_chapters_handler(orch, from_ch):
                    return handle_delete_chapters(orch, from_ch, _t)

                delete_btn.click(
                    fn=delete_chapters_handler,
                    inputs=[orchestrator_state, delete_from_ch],
                    outputs=[continue_log, orchestrator_state],
                )

                def update_char_handler(orch, name, personality, motivation):
                    return handle_update_character(orch, name, personality, motivation, _t)

                update_char_btn.click(
                    fn=update_char_handler,
                    inputs=[orchestrator_state, char_name_input,
                            char_personality_input, char_motivation_input],
                    outputs=[continue_log, orchestrator_state],
                )

                def enhance_handler(orch, n_sim, w_count):
                    return handle_enhance(orch, n_sim, w_count, _t)

                enhance_btn.click(
                    fn=enhance_handler,
                    inputs=[orchestrator_state, sim_rounds, word_count],
                    outputs=[continue_log, orchestrator_state],
                )

            # ═══════════════════════════════════════
            # TAB: XUẤT FILE
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.export")):
                build_export_tab(_t, orchestrator_state)

            # ═══════════════════════════════════════
            # TAB: ĐỌC TRUYỆN
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.reader")):
                build_reader_tab(_t, orchestrator_state)

            # ═══════════════════════════════════════
            # TAB: PHÂN TÍCH
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.analytics")):
                build_analytics_tab(_t, orchestrator_state)

            # ═══════════════════════════════════════
            # TAB: RE NHANH
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.branching")):
                build_branching_tab(_t, orchestrator_state)

            # ═══════════════════════════════════════
            # TAB: CÀI ĐẶT
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.settings")):
                build_settings_tab(_t, i18n, app)

            # ═══════════════════════════════════════
            # TAB: HƯỚNG DẪN
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.guide")):
                guide_text = "\n\n".join([
                    _t("guide.title"),
                    _t("guide.how_pipeline"),
                    _t("guide.pipeline_diagram"),
                    _t("guide.layer1_title"),
                    _t("guide.layer1_desc"),
                    _t("guide.layer2_title"),
                    _t("guide.layer2_desc"),
                    _t("guide.layer3_title"),
                    _t("guide.layer3_desc"),
                    _t("guide.usage_title"),
                    _t("guide.usage_steps"),
                    _t("guide.api_title"),
                    _t("guide.api_desc"),
                ])
                gr.Markdown(guide_text)

    # Health check endpoint — attached to the Gradio FastAPI sub-app
    @app.app.get("/health")
    async def health_check():
        cfg = ConfigManager()
        llm_ok = bool(cfg.llm.api_key) or cfg.llm.backend_type != "api"
        return JSONResponse({
            "status": "ok",
            "version": "2.3",
            "uptime_seconds": round(time.time() - _START_TIME, 1),
            "services": {
                "llm": llm_ok,
                "tts": cfg.pipeline.tts_provider,
                "image_gen": cfg.pipeline.image_provider,
            },
        })

    return app
