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
    """Generate progress bar HTML. layer: 0=idle, 1/2/3=active layer."""
    segments = []
    labels = [_t("progress.layer1"), _t("progress.layer2"), _t("progress.layer3")]
    for i in range(3):
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
    if "LAYER 3" in normalized or "STORYBOARD" in normalized or "VIDEO" in normalized:
        return 3
    if "LAYER 2" in normalized or "MO PHONG" in normalized or "ENHANCE" in normalized:
        return 2
    if "LAYER 1" in normalized or "TAO TRUYEN" in normalized or "CHUONG" in normalized:
        return 1
    return 0


def create_ui():
    """Tạo giao diện Gradio."""

    config = ConfigManager()

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
                        # Quick start section
                        gr.Markdown(_t("section.quick_start"))
                        genre_input = gr.Dropdown(
                            choices=_genres(), value=_genres()[0], label=_t("label.genre"),
                        )
                        template_dropdown = gr.Dropdown(
                            label=_t("label.template"),
                            choices=[], interactive=True,
                            info=_t("label.template_info"),
                        )
                        quick_start_btn = gr.Button(
                            _t("btn.create_now"), variant="primary", size="lg",
                        )

                        gr.Markdown(_t("section.story_info"))
                        title_input = gr.Textbox(
                            label=_t("label.title"), placeholder=_t("label.title_placeholder"),
                        )
                        style_input = gr.Dropdown(
                            choices=_styles(), value=_styles()[0],
                            label=_t("label.style"),
                        )
                        idea_input = gr.Textbox(
                            label=_t("label.idea"),
                            placeholder=_t("label.idea_placeholder"),
                            lines=4,
                        )

                        gr.Markdown(_t("section.config"))
                        num_chapters = gr.Slider(
                            1, 50, value=5, step=1, label=_t("label.num_chapters"),
                        )
                        num_characters = gr.Slider(
                            2, 15, value=5, step=1, label=_t("label.num_characters"),
                        )
                        word_count = gr.Slider(
                            500, 5000, value=2000, step=100,
                            label=_t("label.word_count"),
                        )

                        gr.Markdown(_t("section.layer2"))
                        sim_rounds = gr.Slider(
                            1, 10, value=3, step=1,
                            label=_t("label.sim_rounds"),
                        )
                        drama_level = gr.Dropdown(
                            choices=_drama_levels(), value=_drama_levels()[2],
                            label=_t("label.drama_level"),
                        )

                        gr.Markdown(_t("section.layer3"))
                        shots_per_ch = gr.Slider(
                            4, 20, value=8, step=1,
                            label=_t("label.shots_per_ch"),
                        )

                        gr.Markdown(_t("section.agent_review"))
                        enable_agents_cb = gr.Checkbox(
                            value=True,
                            label=_t("label.enable_agents"),
                        )
                        enable_scoring_cb = gr.Checkbox(
                            value=True,
                            label=_t("label.enable_scoring"),
                        )

                        run_btn = gr.Button(
                            _t("btn.run_pipeline"), variant="primary", size="lg",
                        )

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

                        # Output tabs (6 → 4)
                        with gr.Tabs():
                            with gr.TabItem(_t("tab.story")):
                                gr.Markdown(_t("output.draft_header"))
                                draft_output = gr.Textbox(
                                    label=_t("label.draft"), lines=15, interactive=False,
                                )
                                gr.Markdown(_t("output.enhanced_header"))
                                enhanced_output = gr.Textbox(
                                    label=_t("label.enhanced"), lines=15,
                                    interactive=False,
                                )
                            with gr.TabItem(_t("tab.simulation")):
                                sim_output = gr.Textbox(
                                    label=_t("label.sim_result"), lines=20,
                                    interactive=False,
                                )
                            with gr.TabItem(_t("tab.video")):
                                video_output = gr.Textbox(
                                    label=_t("label.storyboard"), lines=20,
                                    interactive=False,
                                )
                                gr.Markdown(_t("output.video_export"))
                                video_export_btn = gr.Button(
                                    _t("btn.export_video"), variant="secondary",
                                )
                                video_export_file = gr.File(
                                    label=_t("label.video_assets"),
                                )
                            with gr.TabItem(_t("tab.review")):
                                agent_output = gr.Textbox(
                                    label=_t("label.agent_result"), lines=12,
                                    interactive=False,
                                )
                                quality_output = gr.Markdown(
                                    value=_t("output.no_quality"),
                                )

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
                                label=_t("label.resume_checkpoint"), choices=[], interactive=True,
                            )
                            refresh_ckpt_btn = gr.Button(_t("btn.refresh"), scale=0)
                        resume_btn = gr.Button(_t("btn.resume"), variant="secondary")

                # State
                orchestrator_state = gr.State(None)

                def _format_output(output, logs, orch):
                    """Format PipelineOutput for UI display. Returns 11-tuple."""
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

                        # Show improvement delta if both layers scored
                        if len(output.quality_scores) >= 2:
                            l1 = output.quality_scores[0].overall
                            l2 = output.quality_scores[1].overall
                            diff = l2 - l1
                            sign = "+" if diff > 0 else ""
                            quality_text += _t("quality.improvement", sign=sign, diff=f"{diff:.1f}") + "\n"

                    status = "done" if output else "error"
                    status_label = _t("status.done") if output else _t("status.error")
                    return (
                        f'<span class="status-badge status-{status}">{_html.escape(status_label)}</span>',
                        _progress_html(4 if output else 0, _t("status.complete_label") if output else ""),
                        "",  # clear live preview
                        "\n".join(output.logs if output else logs),
                        draft_text, sim_text, enhanced_text, video_text, agent_text,
                        quality_text or _t("output.no_quality_alt"), orch,
                    )

                def run_pipeline(
                    title, genre, style, idea, n_chapters, n_chars,
                    w_count, n_sim, _drama, n_shots, agents_enabled,
                    scoring_enabled,
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
                            "", "\n".join(errors), "", "", "", "", "", "", None,
                        )
                        return

                    orch = PipelineOrchestrator()
                    logs = []
                    progress_queue = queue.Queue()
                    stream_text = [""]  # mutable for closure

                    def on_progress(msg):
                        logs.append(msg)
                        progress_queue.put(("log", msg))

                    # Throttled stream callback (200ms batches)
                    last_stream_time = [0.0]

                    def on_stream(partial_text):
                        stream_text[0] = partial_text
                        now = time.time()
                        if now - last_stream_time[0] > 0.2:
                            progress_queue.put(("stream", partial_text))
                            last_stream_time[0] = now

                    # Chạy pipeline trong thread
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

                    # Queue-based progress + stream updates
                    current_preview = ""
                    while thread.is_alive():
                        try:
                            msg_type, msg_data = progress_queue.get(timeout=0.1)
                            # Drain remaining
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
                                "", "", "", "", "", "", None,
                            )
                        except queue.Empty:
                            continue

                    thread.join()

                    # Flush final stream content before clearing preview
                    if stream_text[0]:
                        layer = _detect_layer(logs[-1]) if logs else 0
                        yield (
                            _status_badge("status-running", "status.running"),
                            _progress_html(layer, logs[-1] if logs else ""),
                            stream_text[0], "\n".join(logs),
                            "", "", "", "", "", "", None,
                        )

                    output = result[0]
                    yield _format_output(output, logs, orch)

                run_btn.click(
                    fn=run_pipeline,
                    inputs=[
                        title_input, genre_input, style_input, idea_input,
                        num_chapters, num_characters, word_count,
                        sim_rounds, drama_level, shots_per_ch, enable_agents_cb,
                        enable_scoring_cb,
                    ],
                    outputs=[
                        status_html, progress_bar, live_preview, progress_log,
                        draft_output, sim_output, enhanced_output, video_output,
                        agent_output, quality_output, orchestrator_state,
                    ],
                )

                # Template handlers
                templates_data = _load_templates()

                def update_template_choices(genre):
                    """Update template dropdown when genre changes."""
                    genre_templates = templates_data.get(genre, [])
                    choices = [t["title"] for t in genre_templates]
                    return gr.update(choices=choices, value=choices[0] if choices else None)

                def apply_template(genre, template_title):
                    """Auto-fill form fields from selected template."""
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

                genre_input.change(
                    fn=update_template_choices,
                    inputs=[genre_input],
                    outputs=[template_dropdown],
                )
                template_dropdown.change(
                    fn=apply_template,
                    inputs=[genre_input, template_dropdown],
                    outputs=[title_input, style_input, idea_input,
                             num_chapters, num_characters, word_count],
                )

                # Quick start — select template then run pipeline
                quick_start_btn.click(
                    fn=run_pipeline,
                    inputs=[
                        title_input, genre_input, style_input, idea_input,
                        num_chapters, num_characters, word_count,
                        sim_rounds, drama_level, shots_per_ch, enable_agents_cb,
                        enable_scoring_cb,
                    ],
                    outputs=[
                        status_html, progress_bar, live_preview, progress_log,
                        draft_output, sim_output, enhanced_output, video_output,
                        agent_output, quality_output, orchestrator_state,
                    ],
                )

                # Load initial templates for default genre
                app.load(
                    fn=update_template_choices,
                    inputs=[genre_input],
                    outputs=[template_dropdown],
                )

                def export_files(orch, formats):
                    if orch is None:
                        return None
                    try:
                        paths = orch.export_output(formats=formats)
                        return paths if paths else None
                    except Exception as e:
                        logger.error(f"Export failed: {e}")
                        return None

                def export_zip_handler(orch, formats):
                    if orch is None:
                        return None
                    try:
                        zip_path = orch.export_zip(formats=formats)
                        return [zip_path] if zip_path else None
                    except Exception as e:
                        logger.error(f"ZIP export failed: {e}")
                        return None

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
                    try:
                        zip_path = orch.export_video_assets()
                        if not zip_path:
                            gr.Info(_t("info.no_video_script"))
                        return zip_path if zip_path else None
                    except Exception as e:
                        logger.error(f"Video asset export failed: {e}")
                        return None

                video_export_btn.click(
                    fn=export_video_assets,
                    inputs=[orchestrator_state],
                    outputs=[video_export_file],
                )

                def refresh_checkpoints():
                    ckpts = PipelineOrchestrator.list_checkpoints()
                    choices = [f"{c['file']} ({c['modified']}, {c['size_kb']}KB)" for c in ckpts]
                    return gr.update(choices=choices, value=choices[0] if choices else None)

                refresh_ckpt_btn.click(fn=refresh_checkpoints, outputs=[checkpoint_dropdown])

                def resume_pipeline(ckpt_choice, n_sim, n_shots, w_count, agents_enabled):
                    if not ckpt_choice:
                        yield (
                            _status_badge("status-error", "status.error"),
                            _progress_html(0),
                            "", _t("error.select_checkpoint"), "", "", "", "", "", "", None,
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
                                "", "", "", "", "", "", None,
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
                            "", "", "", "", "", "", None,
                        )

                    output = result[0]
                    yield _format_output(output, logs, orch)

                resume_btn.click(
                    fn=resume_pipeline,
                    inputs=[checkpoint_dropdown, sim_rounds, shots_per_ch, word_count, enable_agents_cb],
                    outputs=[
                        status_html, progress_bar, live_preview, progress_log,
                        draft_output, sim_output, enhanced_output, video_output,
                        agent_output, quality_output, orchestrator_state,
                    ],
                )

            # ═══════════════════════════════════════
            # TAB 2: CÀI ĐẶT
            # ═══════════════════════════════════════
            with gr.TabItem(_t("tab.settings")):
                # Language selector at top
                gr.Markdown(f"### {_t('label.language')}")
                from services.i18n import SUPPORTED_LANGUAGES
                lang_choices = [f"{v} ({k})" for k, v in SUPPORTED_LANGUAGES.items()]
                current_lang_display = f"{SUPPORTED_LANGUAGES.get(i18n.lang, 'vi')} ({i18n.lang})"
                language_selector = gr.Dropdown(
                    choices=lang_choices,
                    value=current_lang_display,
                    label=_t("label.language"),
                    info=_t("settings.language_restart"),
                )

                gr.Markdown(_t("settings.api_config"))
                api_key = gr.Textbox(
                    label=_t("settings.api_key"),
                    value=config.llm.api_key,
                    type="password",
                )
                base_url = gr.Textbox(
                    label=_t("settings.base_url"),
                    value=config.llm.base_url,
                )
                model_name = gr.Textbox(
                    label=_t("settings.model"),
                    value=config.llm.model,
                )
                temperature = gr.Slider(
                    0, 2, value=config.llm.temperature, step=0.1,
                    label=_t("settings.temperature"),
                )
                max_tokens = gr.Slider(
                    1024, 16384, value=config.llm.max_tokens, step=512,
                    label=_t("settings.max_tokens"),
                )

                gr.Markdown(_t("settings.cheap_model"))
                cheap_model = gr.Textbox(
                    label=_t("settings.cheap_model_label"),
                    value=config.llm.cheap_model,
                    placeholder=_t("settings.cheap_model_placeholder"),
                )
                cheap_base_url = gr.Textbox(
                    label=_t("settings.cheap_url_label"),
                    value=config.llm.cheap_base_url,
                    placeholder=_t("settings.cheap_url_placeholder"),
                )

                gr.Markdown(_t("settings.backend"))
                backend_type = gr.Radio(
                    choices=["api", "web"],
                    value=config.llm.backend_type,
                    label=_t("settings.backend_label"),
                    info=_t("settings.backend_info"),
                )

                # Web auth controls
                gr.Markdown(_t("settings.web_auth"))
                web_auth_status = gr.Textbox(
                    label=_t("settings.auth_status"), interactive=False,
                    value=_t("settings.not_logged_in"),
                )
                with gr.Row():
                    launch_chrome_btn = gr.Button(_t("btn.launch_chrome"))
                    capture_btn = gr.Button(_t("btn.capture_creds"), variant="primary")
                clear_auth_btn = gr.Button(_t("btn.clear_creds"), variant="stop", size="sm")

                def launch_chrome():
                    from services.browser_auth import BrowserAuth
                    auth = BrowserAuth()
                    ok, msg = auth.launch_chrome()
                    return msg

                def capture_credentials():
                    """Capture credentials in background thread to avoid UI blocking."""
                    from services.browser_auth import BrowserAuth
                    auth = BrowserAuth()
                    result = [None]

                    def _run():
                        result[0] = auth.capture_deepseek_credentials(timeout=300)

                    thread = threading.Thread(target=_run)
                    thread.start()

                    yield _t("settings.waiting_login")
                    while thread.is_alive():
                        time.sleep(2)
                        if auth.is_authenticated():
                            break
                        yield _t("settings.waiting_login")

                    thread.join(timeout=5)
                    if result[0]:
                        ok, msg = result[0]
                        yield msg
                    else:
                        yield _t("settings.login_timeout")

                def clear_credentials():
                    from services.browser_auth import BrowserAuth
                    auth = BrowserAuth()
                    auth.clear_credentials()
                    return _t("settings.creds_cleared")

                def check_auth_status():
                    from services.browser_auth import BrowserAuth
                    auth = BrowserAuth()
                    if auth.is_authenticated():
                        creds = auth.get_credentials()
                        updated = creds.get("updated_at", "?") if creds else "?"
                        return _t("settings.logged_in", time=updated)
                    return _t("settings.not_logged_in")

                launch_chrome_btn.click(fn=launch_chrome, outputs=[web_auth_status])
                capture_btn.click(fn=capture_credentials, outputs=[web_auth_status])
                clear_auth_btn.click(fn=clear_credentials, outputs=[web_auth_status])
                app.load(fn=check_auth_status, outputs=[web_auth_status])

                gr.Markdown("---")
                connection_status = gr.Textbox(
                    label=_t("settings.connection_status"), interactive=False,
                )
                test_connection_btn = gr.Button(_t("btn.test_connection"))

                def test_connection(backend, key, url, model):
                    cfg = ConfigManager()
                    cfg.llm.backend_type = backend
                    if backend == "api":
                        cfg.llm.api_key = key
                        cfg.llm.base_url = url
                        cfg.llm.model = model
                    from services.llm_client import LLMClient
                    LLMClient._instance = None
                    client = LLMClient()
                    ok, msg = client.check_connection()
                    return f"{'OK' if ok else 'LOI'}: {msg}"

                test_connection_btn.click(
                    fn=test_connection,
                    inputs=[backend_type, api_key, base_url, model_name],
                    outputs=[connection_status],
                )

                gr.Markdown(_t("settings.cache_title"))
                cache_info = gr.Textbox(label=_t("settings.cache_label"), interactive=False)
                with gr.Row():
                    cache_stats_btn = gr.Button(_t("btn.cache_stats"))
                    cache_clear_btn = gr.Button(_t("btn.clear_cache"), variant="stop")

                def show_cache_stats():
                    try:
                        from services.llm_cache import LLMCache
                        stats = LLMCache(ttl_days=ConfigManager().llm.cache_ttl_days).stats()
                        return f"Total: {stats['total']} | Valid: {stats['valid']} | Expired: {stats['expired']}"
                    except Exception as e:
                        return f"Loi: {e}"

                def clear_cache():
                    try:
                        from services.llm_cache import LLMCache
                        LLMCache().clear()
                        return "Da xoa cache!"
                    except Exception as e:
                        return f"Loi: {e}"

                cache_stats_btn.click(fn=show_cache_stats, outputs=[cache_info])
                cache_clear_btn.click(fn=clear_cache, outputs=[cache_info])

                save_btn = gr.Button(_t("btn.save_settings"), variant="primary")
                save_status = gr.Textbox(label=_t("settings.status_label"), interactive=False)

                def save_settings(key, url, model, temp, tokens,
                                  cheap_m, cheap_url, backend, lang_choice):
                    cfg = ConfigManager()
                    cfg.llm.api_key = key
                    cfg.llm.base_url = url
                    cfg.llm.model = model
                    cfg.llm.temperature = temp
                    cfg.llm.max_tokens = int(tokens)
                    cfg.llm.cheap_model = cheap_m
                    cfg.llm.cheap_base_url = cheap_url
                    cfg.llm.backend_type = backend
                    # Save language
                    if lang_choice:
                        lang_code = lang_choice.split("(")[-1].rstrip(")")
                        cfg.pipeline.language = lang_code
                        i18n.set_language(lang_code)
                    cfg.save()
                    # Reset LLM client singleton
                    from services.llm_client import LLMClient
                    LLMClient._instance = None
                    return _t("settings.saved")

                save_btn.click(
                    fn=save_settings,
                    inputs=[api_key, base_url, model_name, temperature, max_tokens,
                            cheap_model, cheap_base_url, backend_type, language_selector],
                    outputs=[save_status],
                )

            # ═══════════════════════════════════════
            # TAB 3: HƯỚNG DẪN
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
