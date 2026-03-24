"""StoryForge - Tạo truyện kịch tính và kịch bản video tự động.

Pipeline 3 lớp:
  Layer 1 (create-story): Tạo truyện từ ý tưởng
  Layer 2 (MiroFish-inspired): Mô phỏng nhân vật tăng kịch tính
  Layer 3 (waoowaoo-inspired): Tạo storyboard và kịch bản video
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
    build_account_tab,
    build_settings_tab,
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("storyforge.log", encoding="utf-8"),
    ],
)
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
    "data", "templates", "story_templates.json",
)


def _load_templates() -> dict:
    """Load story templates from JSON file."""
    if os.path.exists(TEMPLATES_PATH):
        try:
            with open(TEMPLATES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _progress_html(layer: int = 0, step: str = "") -> str:
    """Generate progress bar HTML. layer: 0=idle, 1/2/3/4=active layer."""
    segments = []
    labels = [_t("progress.layer1"), _t("progress.layer2"), _t("progress.layer3"), "Media"]
    for i in range(4):
        lnum = i + 1
        if layer > lnum:
            cls = "progress-segment done"
        elif layer == lnum:
            cls = "progress-segment active"
        else:
            cls = "progress-segment"
        segments.append(f'<div class="{cls}">{labels[i]}</div>')
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


def create_ui():
    """Tạo giao diện Gradio."""

    with gr.Blocks(
        title="StoryForge",
        theme=gr.themes.Soft(),
        css="""
        .pipeline-header { text-align: center; margin-bottom: 20px; }
        .layer-box { border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin: 10px 0; }

        /* Progress bar */
        .progress-bar-container {
            display: flex; gap: 4px; margin: 10px 0; height: 32px;
            background: #f0f0f0; border-radius: 8px; overflow: hidden;
        }
        .progress-segment {
            flex: 1; display: flex; align-items: center; justify-content: center;
            font-size: 12px; font-weight: 600; color: #666;
            transition: all 0.5s ease; background: #e8e8e8;
        }
        .progress-segment.active {
            background: #3b82f6; color: white;
            animation: pulse-bg 2s infinite;
        }
        .progress-segment.done { background: #22c55e; color: white; }
        @keyframes pulse-bg {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        .progress-step-text {
            text-align: center; font-size: 13px; color: #555;
            margin: 4px 0 8px 0; min-height: 20px;
        }

        /* Status badge */
        .status-badge {
            display: inline-block; padding: 4px 12px; border-radius: 12px;
            font-size: 12px; font-weight: 600;
        }
        .status-idle { background: #e5e7eb; color: #6b7280; }
        .status-running { background: #dbeafe; color: #2563eb; animation: pulse-bg 2s infinite; }
        .status-done { background: #dcfce7; color: #16a34a; }
        .status-error { background: #fee2e2; color: #dc2626; }

        /* Mobile responsive */
        @media (max-width: 768px) {
            .gr-row { flex-direction: column !important; }
            .gr-column { min-width: 100% !important; }
            .progress-segment { font-size: 10px; }
        }
        /* Touch-friendly */
        @media (max-width: 768px) {
            .gradio-button { min-height: 44px; }
        }
        @media (max-width: 480px) {
            .tab-nav { flex-wrap: wrap; }
            .tab-nav button { flex: 1 1 45%; font-size: 11px; }
        }
        /* Compact mode */
        .compact-mode .prose { font-size: 14px; }
        .compact-mode .block { padding: 8px !important; }
        """,
    ) as app:
        gr.Markdown(
            f"# {_t('app.title')}\n### {_t('app.subtitle')}\n\n{_t('app.pipeline_desc')}",
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
                        enable_scoring_cb = form["enable_scoring_cb"]  # enable_scoring_cb = gr.Checkbox (see ui/tabs/pipeline_tab.py)
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
                                quality_output = rev["quality_output"]  # quality_output = gr.Markdown (see ui/tabs/review_tab.py)

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
                # Shared user state (also used in account tab)
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
                    scoring_enabled, user_state_data=None,
                ):
                    errors = []
                    if not idea or len(idea.strip()) < 10:
                        errors.append(_t("error.idea_too_short"))
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
                        except Exception:
                            pass  # Non-blocking: skip credit check on error

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
                    enable_scoring_cb, user_state,
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
            # TAB: TÀI KHOẢN
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.account")):
                build_account_tab(_t, orchestrator_state, user_state=user_state)

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

    return app


def main():
    app = create_ui()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )


if __name__ == "__main__":
    main()
