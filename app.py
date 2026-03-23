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

# Genres tiếng Việt
GENRES = [
    "Tiên Hiệp", "Huyền Huyễn", "Kiếm Hiệp", "Đô Thị",
    "Ngôn Tình", "Xuyên Không", "Trọng Sinh", "Hệ Thống",
    "Khoa Huyễn", "Đồng Nhân", "Lịch Sử", "Quân Sự",
    "Linh Dị", "Trinh Thám", "Hài Hước", "Võng Du",
    "Dị Giới", "Mạt Thế", "Điền Văn", "Cung Đấu",
]

STYLES = [
    "Miêu tả chi tiết",
    "Đối thoại sắc bén",
    "Hành động mãnh liệt",
    "Trữ tình lãng mạn",
    "U ám kịch tính",
]

DRAMA_LEVELS = ["thấp", "trung bình", "cao"]

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
    labels = ["Layer 1: Tao truyen", "Layer 2: Mo phong", "Layer 3: Video"]
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
            """
            # StoryForge
            ### Tạo truyện kịch tính & kịch bản video tự động

            **Pipeline 3 lớp:**
            Layer 1 → Tạo truyện | Layer 2 → Mô phỏng tăng kịch tính | Layer 3 → Kịch bản video
            """,
            elem_classes="pipeline-header",
        )

        with gr.Tabs():
            # ═══════════════════════════════════════
            # TAB 1: PIPELINE ĐẦY ĐỦ
            # ═══════════════════════════════════════
            with gr.TabItem("Pipeline Đầy Đủ"):
                with gr.Row():
                    with gr.Column(scale=1):
                        # Quick start section
                        gr.Markdown("### Bat dau nhanh")
                        genre_input = gr.Dropdown(
                            choices=GENRES, value="Tiên Hiệp", label="Thể loại",
                        )
                        template_dropdown = gr.Dropdown(
                            label="Mau truyen (template)",
                            choices=[], interactive=True,
                            info="Chon mau hoac tu nhap y tuong ben duoi",
                        )
                        quick_start_btn = gr.Button(
                            "Tao ngay!", variant="primary", size="lg",
                        )

                        gr.Markdown("### Thông tin truyện")
                        title_input = gr.Textbox(
                            label="Tiêu đề", placeholder="Để trống để AI đề xuất",
                        )
                        style_input = gr.Dropdown(
                            choices=STYLES, value="Miêu tả chi tiết",
                            label="Phong cách viết",
                        )
                        idea_input = gr.Textbox(
                            label="Ý tưởng / Mô tả truyện",
                            placeholder="Mô tả ý tưởng câu truyện của bạn...",
                            lines=4,
                        )

                        gr.Markdown("### Cấu hình")
                        num_chapters = gr.Slider(
                            1, 50, value=5, step=1, label="Số chương",
                        )
                        num_characters = gr.Slider(
                            2, 15, value=5, step=1, label="Số nhân vật",
                        )
                        word_count = gr.Slider(
                            500, 5000, value=2000, step=100,
                            label="Số từ mỗi chương",
                        )

                        gr.Markdown("### Layer 2 - Mô phỏng")
                        sim_rounds = gr.Slider(
                            1, 10, value=3, step=1,
                            label="Số vòng mô phỏng",
                        )
                        drama_level = gr.Dropdown(
                            choices=DRAMA_LEVELS, value="cao",
                            label="Mức kịch tích",
                        )

                        gr.Markdown("### Layer 3 - Video")
                        shots_per_ch = gr.Slider(
                            4, 20, value=8, step=1,
                            label="Số shot mỗi chương",
                        )

                        gr.Markdown("### Agent Review")
                        enable_agents_cb = gr.Checkbox(
                            value=True,
                            label="Bat phong ban danh gia (Agent Review)",
                        )
                        enable_scoring_cb = gr.Checkbox(
                            value=True,
                            label="Cham diem tu dong (Quality Metrics)",
                        )

                        run_btn = gr.Button(
                            "Chay Pipeline", variant="primary", size="lg",
                        )

                    with gr.Column(scale=2):
                        # Status + Progress bar
                        status_html = gr.HTML(
                            value='<span class="status-badge status-idle">San sang</span>',
                        )
                        progress_bar = gr.HTML(value=_progress_html(0))

                        # Live preview
                        live_preview = gr.Textbox(
                            label="Live Preview (dang viet...)",
                            lines=8, interactive=False,
                        )

                        # Collapsed detail log
                        with gr.Accordion("Chi tiet tien trinh", open=False):
                            progress_log = gr.Textbox(
                                label="Log", lines=8, interactive=False,
                            )

                        # Output tabs (6 → 4)
                        with gr.Tabs():
                            with gr.TabItem("Truyen"):
                                gr.Markdown("#### Ban thao (Layer 1)")
                                draft_output = gr.Textbox(
                                    label="Truyen goc", lines=15, interactive=False,
                                )
                                gr.Markdown("#### Phien ban kich tinh (Layer 2)")
                                enhanced_output = gr.Textbox(
                                    label="Truyen tang cuong", lines=15,
                                    interactive=False,
                                )
                            with gr.TabItem("Mo Phong"):
                                sim_output = gr.Textbox(
                                    label="Ket qua mo phong", lines=20,
                                    interactive=False,
                                )
                            with gr.TabItem("Video"):
                                video_output = gr.Textbox(
                                    label="Storyboard & Script", lines=20,
                                    interactive=False,
                                )
                                gr.Markdown("#### Xuat Video Assets")
                                video_export_btn = gr.Button(
                                    "Xuat Video Assets (ZIP)", variant="secondary",
                                )
                                video_export_file = gr.File(
                                    label="Video assets download",
                                )
                            with gr.TabItem("Danh Gia"):
                                agent_output = gr.Textbox(
                                    label="Ket qua danh gia agent", lines=12,
                                    interactive=False,
                                )
                                quality_output = gr.Markdown(
                                    value="*Chua co diem. Chay pipeline voi 'Cham diem tu dong' bat.*",
                                )

                        export_formats = gr.CheckboxGroup(
                            choices=["TXT", "Markdown", "JSON"],
                            value=["TXT", "Markdown", "JSON"],
                            label="Dinh dang xuat",
                        )
                        with gr.Row():
                            export_btn = gr.Button("Xuat file")
                            zip_btn = gr.Button("Download All (ZIP)")
                        export_files_output = gr.File(
                            label="File xuat", file_count="multiple",
                        )

                        gr.Markdown("### Checkpoint / Resume")
                        with gr.Row():
                            checkpoint_dropdown = gr.Dropdown(
                                label="Resume tu checkpoint", choices=[], interactive=True,
                            )
                            refresh_ckpt_btn = gr.Button("Refresh", scale=0)
                        resume_btn = gr.Button("Resume Pipeline", variant="secondary")

                # State
                orchestrator_state = gr.State(None)

                def _format_output(output, logs, orch):
                    """Format PipelineOutput for UI display. Returns 11-tuple."""
                    draft_text = ""
                    if output and output.story_draft:
                        d = output.story_draft
                        draft_text = f"# {d.title}\n\n"
                        draft_text += f"**Thể loại:** {d.genre}\n"
                        draft_text += f"**Tóm tắt:** {d.synopsis}\n\n"
                        draft_text += f"**Nhân vật:** {', '.join(c.name for c in d.characters)}\n\n"
                        for ch in d.chapters:
                            draft_text += f"\n---\n## Chương {ch.chapter_number}: {ch.title}\n\n"
                            draft_text += ch.content[:2000] + "...\n"

                    sim_text = ""
                    if output and output.simulation_result:
                        s = output.simulation_result
                        sim_text = "## Kết quả Mô phỏng\n\n"
                        sim_text += f"**Số sự kiện kịch tính:** {len(s.events)}\n"
                        sim_text += f"**Số bài viết agent:** {len(s.agent_posts)}\n\n"
                        sim_text += "### Sự kiện nổi bật:\n"
                        for e in s.events[:10]:
                            sim_text += (
                                f"- [{e.event_type}] {e.description} "
                                f"(kịch tính: {e.drama_score:.1f})\n"
                            )
                        sim_text += "\n### Gợi ý tăng kịch tính:\n"
                        for sug in s.drama_suggestions[:5]:
                            sim_text += f"- {sug}\n"

                    enhanced_text = ""
                    if output and output.enhanced_story:
                        es = output.enhanced_story
                        enhanced_text = f"# {es.title} (Phiên bản kịch tính)\n"
                        enhanced_text += f"**Điểm kịch tính:** {es.drama_score:.2f}/1.0\n\n"
                        for ch in es.chapters:
                            enhanced_text += f"\n---\n## Chương {ch.chapter_number}: {ch.title}\n\n"
                            enhanced_text += ch.content[:2000] + "...\n"

                    video_text = ""
                    if output and output.video_script:
                        vs = output.video_script
                        video_text = f"# Kịch bản Video: {vs.title}\n"
                        video_text += f"**Tổng thời lượng:** ~{vs.total_duration_seconds/60:.1f} phút\n"
                        video_text += f"**Tổng panels:** {len(vs.panels)}\n"
                        video_text += f"**Dòng thoại:** {len(vs.voice_lines)}\n\n"
                        for p in vs.panels[:20]:
                            video_text += (
                                f"### Panel {p.panel_number} (Ch.{p.chapter_number})\n"
                                f"- **Shot:** {p.shot_type.value} | **Camera:** {p.camera_movement}\n"
                                f"- **Mô tả:** {p.description}\n"
                            )
                            if p.dialogue:
                                video_text += f"- **Thoại:** {p.dialogue}\n"
                            if p.image_prompt:
                                video_text += f"- **Image prompt:** {p.image_prompt}\n"
                            video_text += "\n"

                    agent_text = ""
                    if output and output.reviews:
                        agent_text = "## Ket qua Danh gia Agent\n\n"
                        for r in output.reviews:
                            status = "PASS" if r.approved else "FAIL"
                            agent_text += f"### {r.agent_name} (Layer {r.layer}, Vong {r.iteration})\n"
                            agent_text += f"- Diem: {r.score:.1f}/1.0 [{status}]\n"
                            if r.issues:
                                agent_text += f"- Van de: {'; '.join(r.issues[:3])}\n"
                            if r.suggestions:
                                agent_text += f"- Goi y: {'; '.join(r.suggestions[:3])}\n"
                            agent_text += "\n"

                    quality_text = ""
                    if output and output.quality_scores:
                        quality_text = "## Diem Chat Luong Truyen\n\n"
                        for qs in output.quality_scores:
                            quality_text += f"### Layer {qs.scoring_layer} — Tong: {qs.overall:.1f}/5\n\n"
                            quality_text += (
                                f"| Chi tieu | Diem |\n|---|---|\n"
                                f"| Mach lac | {qs.avg_coherence:.1f} |\n"
                                f"| Nhan vat | {qs.avg_character:.1f} |\n"
                                f"| Kich tinh | {qs.avg_drama:.1f} |\n"
                                f"| Van phong | {qs.avg_writing:.1f} |\n\n"
                            )
                            quality_text += f"**Chuong yeu nhat:** {qs.weakest_chapter}\n\n"
                            quality_text += "| Chuong | Mach lac | Nhan vat | Kich tinh | Van phong | Tong | Ghi chu |\n"
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
                            quality_text += f"**Cai thien Layer 1 → 2:** {sign}{diff:.1f} diem\n"

                    status = "done" if output else "error"
                    status_label = "Hoan thanh!" if output else "Loi"
                    return (
                        f'<span class="status-badge status-{status}">{status_label}</span>',
                        _progress_html(4 if output else 0, "Hoan thanh" if output else ""),
                        "",  # clear live preview
                        "\n".join(output.logs if output else logs),
                        draft_text, sim_text, enhanced_text, video_text, agent_text,
                        quality_text or "*Khong co diem chat luong.*", orch,
                    )

                def run_pipeline(
                    title, genre, style, idea, n_chapters, n_chars,
                    w_count, n_sim, _drama, n_shots, agents_enabled,
                    scoring_enabled,
                ):
                    errors = []
                    if not idea or len(idea.strip()) < 10:
                        errors.append("Y tuong can it nhat 10 ky tu")
                    if n_chapters < 1 or n_chapters > 50:
                        errors.append("So chuong phai tu 1-50")
                    if errors:
                        yield (
                            '<span class="status-badge status-error">Loi</span>',
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
                            title=title or f"Truyện {genre}",
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
                                '<span class="status-badge status-running">Dang chay...</span>',
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
                            '<span class="status-badge status-running">Dang chay...</span>',
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
                        gr.Info("Hay chay pipeline truoc khi xuat video assets.")
                        return None
                    try:
                        zip_path = orch.export_video_assets()
                        if not zip_path:
                            gr.Info("Khong co video script. Hay chay pipeline voi Layer 3.")
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
                            '<span class="status-badge status-error">Loi</span>',
                            _progress_html(0),
                            "", "Chon checkpoint truoc!", "", "", "", "", "", "", None,
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
                                '<span class="status-badge status-running">Dang chay...</span>',
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
                            '<span class="status-badge status-running">Dang chay...</span>',
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
            with gr.TabItem("Cài Đặt"):
                gr.Markdown("### Cấu hình API")
                api_key = gr.Textbox(
                    label="API Key",
                    value=config.llm.api_key,
                    type="password",
                )
                base_url = gr.Textbox(
                    label="Base URL",
                    value=config.llm.base_url,
                )
                model_name = gr.Textbox(
                    label="Model",
                    value=config.llm.model,
                )
                temperature = gr.Slider(
                    0, 2, value=config.llm.temperature, step=0.1,
                    label="Temperature",
                )
                max_tokens = gr.Slider(
                    1024, 16384, value=config.llm.max_tokens, step=512,
                    label="Max Tokens",
                )

                gr.Markdown("### Model gia re (tom tat/phan tich)")
                cheap_model = gr.Textbox(
                    label="Cheap Model (de trong = dung model chinh)",
                    value=config.llm.cheap_model,
                    placeholder="vd: gpt-4o-mini, deepseek-chat",
                )
                cheap_base_url = gr.Textbox(
                    label="Base URL cheap model (de trong = dung chung)",
                    value=config.llm.cheap_base_url,
                    placeholder="de trong = dung base URL chinh",
                )

                gr.Markdown("### Backend AI")
                backend_type = gr.Radio(
                    choices=["api", "web"],
                    value=config.llm.backend_type,
                    label="Loai backend",
                    info="api = OpenAI-compatible API | web = Dang nhap trinh duyet (mien phi)",
                )

                # Web auth controls
                gr.Markdown("### Dang nhap qua trinh duyet (Web Auth)")
                web_auth_status = gr.Textbox(
                    label="Trang thai dang nhap", interactive=False,
                    value="Chua dang nhap",
                )
                with gr.Row():
                    launch_chrome_btn = gr.Button("Khoi dong trinh duyet")
                    capture_btn = gr.Button("Bat dau thu thap credentials", variant="primary")
                clear_auth_btn = gr.Button("Xoa credentials", variant="stop", size="sm")

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

                    yield "Dang cho dang nhap... (hay dang nhap DeepSeek trong trinh duyet)"
                    while thread.is_alive():
                        time.sleep(2)
                        if auth.is_authenticated():
                            break
                        yield "Dang cho dang nhap... (hay dang nhap DeepSeek trong trinh duyet)"

                    thread.join(timeout=5)
                    if result[0]:
                        ok, msg = result[0]
                        yield msg
                    else:
                        yield "Het thoi gian hoac loi."

                def clear_credentials():
                    from services.browser_auth import BrowserAuth
                    auth = BrowserAuth()
                    auth.clear_credentials()
                    return "Da xoa credentials."

                def check_auth_status():
                    from services.browser_auth import BrowserAuth
                    auth = BrowserAuth()
                    if auth.is_authenticated():
                        creds = auth.get_credentials()
                        updated = creds.get("updated_at", "?") if creds else "?"
                        return f"Da dang nhap (cap nhat: {updated})"
                    return "Chua dang nhap"

                launch_chrome_btn.click(fn=launch_chrome, outputs=[web_auth_status])
                capture_btn.click(fn=capture_credentials, outputs=[web_auth_status])
                clear_auth_btn.click(fn=clear_credentials, outputs=[web_auth_status])
                app.load(fn=check_auth_status, outputs=[web_auth_status])

                gr.Markdown("---")
                connection_status = gr.Textbox(
                    label="Trang thai ket noi", interactive=False,
                )
                test_connection_btn = gr.Button("Kiem tra ket noi")

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

                gr.Markdown("### Cache LLM")
                cache_info = gr.Textbox(label="Cache info", interactive=False)
                with gr.Row():
                    cache_stats_btn = gr.Button("Xem cache stats")
                    cache_clear_btn = gr.Button("Xoa cache", variant="stop")

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

                save_btn = gr.Button("Luu cai dat", variant="primary")
                save_status = gr.Textbox(label="Trạng thái", interactive=False)

                def save_settings(key, url, model, temp, tokens,
                                  cheap_m, cheap_url, backend):
                    cfg = ConfigManager()
                    cfg.llm.api_key = key
                    cfg.llm.base_url = url
                    cfg.llm.model = model
                    cfg.llm.temperature = temp
                    cfg.llm.max_tokens = int(tokens)
                    cfg.llm.cheap_model = cheap_m
                    cfg.llm.cheap_base_url = cheap_url
                    cfg.llm.backend_type = backend
                    cfg.save()
                    # Reset LLM client singleton
                    from services.llm_client import LLMClient
                    LLMClient._instance = None
                    return "Da luu cai dat!"

                save_btn.click(
                    fn=save_settings,
                    inputs=[api_key, base_url, model_name, temperature, max_tokens,
                            cheap_model, cheap_base_url, backend_type],
                    outputs=[save_status],
                )

            # ═══════════════════════════════════════
            # TAB 3: HƯỚNG DẪN
            # ═══════════════════════════════════════
            with gr.TabItem("Hướng Dẫn"):
                gr.Markdown("""
                ## Hướng dẫn sử dụng StoryForge

                ### Pipeline hoạt động như thế nào?

                ```
                Ý tưởng → [Layer 1: Tạo Truyện] → [Layer 2: Mô Phỏng Kịch Tính] → [Layer 3: Kịch Bản Video] → Output
                ```

                #### Layer 1: Tạo Truyện (create-story)
                - Tạo nhân vật với tính cách, tiểu sử, động lực
                - Xây dựng bối cảnh thế giới
                - Tạo dàn ý chi tiết
                - Viết từng chương tự động

                #### Layer 2: Mô Phỏng Tăng Kịch Tính (MiroFish-inspired)
                - **Phân tích:** Trích xuất mối quan hệ và xung đột giữa nhân vật
                - **Mô phỏng:** Mỗi nhân vật trở thành AI agent tự trị
                - Agents tương tác tự do: đăng suy nghĩ, phản hồi, đối đầu, phản bội
                - Hệ thống đánh giá và trích xuất tình huống kịch tính
                - **Tăng cường:** Viết lại truyện với các yếu tố kịch tích từ mô phỏng

                #### Layer 3: Kịch Bản Video (waoowaoo-inspired)
                - Tạo storyboard: shot, camera, mood cho từng cảnh
                - Tạo image prompt cho AI image generation
                - Tạo kịch bản lồng tiếng với cảm xúc
                - Mô tả hình ảnh nhân vật và bối cảnh

                ### Cách sử dụng
                1. Vào **Cài Đặt** → nhập API Key và chọn model
                2. Vào **Pipeline Đầy Đủ** → nhập ý tưởng truyện
                3. Điều chỉnh các thông số nếu cần
                4. Nhấn **Chạy Pipeline** và đợi
                5. Xem kết quả ở các tab: Truyện Gốc, Mô Phỏng, Truyện Kịch Tính, Kịch Bản Video, Danh Gia (Agents)
                6. Nhấn **Xuất file** để lưu kết quả

                ### API tương thích
                Hỗ trợ mọi API tương thích OpenAI: OpenAI, Anthropic (qua proxy),
                Google Gemini, DeepSeek, Groq, Together AI, OpenRouter, Ollama, v.v.
                """)

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
