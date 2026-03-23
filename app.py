"""Novel Auto Pipeline - Tạo truyện kịch tính và kịch bản video tự động.

Pipeline 3 lớp:
  Layer 1 (create-story): Tạo truyện từ ý tưởng
  Layer 2 (MiroFish-inspired): Mô phỏng nhân vật tăng kịch tính
  Layer 3 (waoowaoo-inspired): Tạo storyboard và kịch bản video
"""

import logging
import threading
import queue
import os
import gradio as gr

from config import ConfigManager
from pipeline.orchestrator import PipelineOrchestrator

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("novel_auto.log", encoding="utf-8"),
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


def create_ui():
    """Tạo giao diện Gradio."""

    config = ConfigManager()

    with gr.Blocks(
        title="Novel Auto Pipeline",
        theme=gr.themes.Soft(),
        css="""
        .pipeline-header { text-align: center; margin-bottom: 20px; }
        .layer-box { border: 1px solid #ddd; border-radius: 8px; padding: 15px; margin: 10px 0; }
        """,
    ) as app:
        gr.Markdown(
            """
            # Novel Auto Pipeline
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
                        gr.Markdown("### Thông tin truyện")
                        title_input = gr.Textbox(
                            label="Tiêu đề", placeholder="Để trống để AI đề xuất",
                        )
                        genre_input = gr.Dropdown(
                            choices=GENRES, value="Tiên Hiệp", label="Thể loại",
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

                        run_btn = gr.Button(
                            "Chay Pipeline", variant="primary", size="lg",
                        )

                    with gr.Column(scale=2):
                        progress_log = gr.Textbox(
                            label="Tiến trình", lines=15, interactive=False,
                        )
                        with gr.Tabs():
                            with gr.TabItem("Truyện Gốc (Layer 1)"):
                                draft_output = gr.Textbox(
                                    label="Bản thảo", lines=20, interactive=False,
                                )
                            with gr.TabItem("Mô Phỏng (Layer 2)"):
                                sim_output = gr.Textbox(
                                    label="Kết quả mô phỏng", lines=20,
                                    interactive=False,
                                )
                            with gr.TabItem("Truyện Kịch Tính (Layer 2)"):
                                enhanced_output = gr.Textbox(
                                    label="Truyện tăng cường", lines=20,
                                    interactive=False,
                                )
                            with gr.TabItem("Kịch Bản Video (Layer 3)"):
                                video_output = gr.Textbox(
                                    label="Storyboard & Script", lines=20,
                                    interactive=False,
                                )
                            with gr.TabItem("Danh Gia (Agents)"):
                                agent_output = gr.Textbox(
                                    label="Ket qua danh gia", lines=20,
                                    interactive=False,
                                )

                        export_formats = gr.CheckboxGroup(
                            choices=["TXT", "Markdown", "JSON"],
                            value=["TXT", "Markdown", "JSON"],
                            label="Dinh dang xuat",
                        )
                        export_btn = gr.Button("Xuat file")
                        export_status = gr.Textbox(
                            label="Trạng thái xuất", interactive=False,
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
                    """Format PipelineOutput for UI display. Returns 7-tuple."""
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

                    return (
                        "\n".join(output.logs if output else logs),
                        draft_text, sim_text, enhanced_text, video_text, agent_text, orch,
                    )

                def run_pipeline(
                    title, genre, style, idea, n_chapters, n_chars,
                    w_count, n_sim, _drama, n_shots, agents_enabled,
                ):
                    errors = []
                    if not idea or len(idea.strip()) < 10:
                        errors.append("Y tuong can it nhat 10 ky tu")
                    if n_chapters < 1 or n_chapters > 50:
                        errors.append("So chuong phai tu 1-50")
                    if errors:
                        yield ("\n".join(errors), "", "", "", "", "", None)
                        return

                    orch = PipelineOrchestrator()
                    logs = []
                    progress_queue = queue.Queue()

                    def on_progress(msg):
                        logs.append(msg)
                        progress_queue.put(msg)

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
                            enable_agents=agents_enabled,
                        )

                    thread = threading.Thread(target=_run)
                    thread.start()

                    # Queue-based progress updates
                    while thread.is_alive():
                        try:
                            progress_queue.get(timeout=0.1)
                            # Drain remaining
                            while not progress_queue.empty():
                                try:
                                    progress_queue.get_nowait()
                                except queue.Empty:
                                    break
                            yield ("\n".join(logs), "", "", "", "", "", None)
                        except queue.Empty:
                            continue

                    thread.join()
                    output = result[0]

                    yield _format_output(output, logs, orch)

                run_btn.click(
                    fn=run_pipeline,
                    inputs=[
                        title_input, genre_input, style_input, idea_input,
                        num_chapters, num_characters, word_count,
                        sim_rounds, drama_level, shots_per_ch, enable_agents_cb,
                    ],
                    outputs=[
                        progress_log, draft_output, sim_output,
                        enhanced_output, video_output, agent_output,
                        orchestrator_state,
                    ],
                )

                def export_files(orch, formats):
                    if orch is None:
                        return "Chua co du lieu de xuat. Hay chay pipeline truoc."
                    try:
                        path = orch.export_output(formats=formats)
                        return f"Da xuat file vao thu muc: {path}"
                    except Exception as e:
                        return f"Loi xuat file: {e}"

                export_btn.click(
                    fn=export_files,
                    inputs=[orchestrator_state, export_formats],
                    outputs=[export_status],
                )

                def refresh_checkpoints():
                    ckpts = PipelineOrchestrator.list_checkpoints()
                    choices = [f"{c['file']} ({c['modified']}, {c['size_kb']}KB)" for c in ckpts]
                    return gr.update(choices=choices, value=choices[0] if choices else None)

                refresh_ckpt_btn.click(fn=refresh_checkpoints, outputs=[checkpoint_dropdown])

                def resume_pipeline(ckpt_choice, n_sim, n_shots, w_count, agents_enabled):
                    if not ckpt_choice:
                        yield ("Chon checkpoint truoc!", "", "", "", "", "", None)
                        return

                    filename = ckpt_choice.split(" (")[0]
                    ckpt_path = os.path.join(PipelineOrchestrator.CHECKPOINT_DIR, filename)

                    orch = PipelineOrchestrator()
                    logs = []
                    progress_q = queue.Queue()

                    def on_progress(msg):
                        logs.append(msg)
                        progress_q.put(msg)

                    result = [None]

                    def _run():
                        result[0] = orch.resume_from_checkpoint(
                            ckpt_path,
                            progress_callback=on_progress,
                            enable_agents=agents_enabled,
                            num_sim_rounds=int(n_sim),
                            shots_per_chapter=int(n_shots),
                            word_count=int(w_count),
                        )

                    thread = threading.Thread(target=_run)
                    thread.start()

                    while thread.is_alive():
                        try:
                            progress_q.get(timeout=0.1)
                            while not progress_q.empty():
                                try:
                                    progress_q.get_nowait()
                                except queue.Empty:
                                    break
                            yield ("\n".join(logs), "", "", "", "", "", None)
                        except queue.Empty:
                            continue

                    thread.join()
                    output = result[0]
                    yield _format_output(output, logs, orch)

                resume_btn.click(
                    fn=resume_pipeline,
                    inputs=[checkpoint_dropdown, sim_rounds, shots_per_ch, word_count, enable_agents_cb],
                    outputs=[progress_log, draft_output, sim_output, enhanced_output, video_output, agent_output, orchestrator_state],
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

                gr.Markdown("### Backend AI")
                backend_type = gr.Radio(
                    choices=["api", "openclaw"],
                    value=config.llm.backend_type,
                    label="Loai backend",
                )
                openclaw_port = gr.Number(
                    value=config.llm.openclaw_port,
                    label="OpenClaw Port",
                    visible=True,
                )
                openclaw_model = gr.Textbox(
                    value=config.llm.openclaw_model,
                    label="OpenClaw Model",
                )
                auto_fallback = gr.Checkbox(
                    value=config.llm.auto_fallback,
                    label="Tu dong chuyen sang API khi OpenClaw loi",
                )

                openclaw_status = gr.Textbox(
                    label="Trang thai OpenClaw", interactive=False,
                )
                test_connection_btn = gr.Button("Kiem tra ket noi")

                def test_connection(backend, key, url, model, oc_port, oc_model):
                    cfg = ConfigManager()
                    cfg.llm.backend_type = backend
                    if backend == "openclaw":
                        cfg.llm.openclaw_port = int(oc_port)
                        cfg.llm.openclaw_model = oc_model
                    else:
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
                    inputs=[backend_type, api_key, base_url, model_name,
                            openclaw_port, openclaw_model],
                    outputs=[openclaw_status],
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
                                  backend, oc_port, oc_model, fallback):
                    cfg = ConfigManager()
                    cfg.llm.api_key = key
                    cfg.llm.base_url = url
                    cfg.llm.model = model
                    cfg.llm.temperature = temp
                    cfg.llm.max_tokens = int(tokens)
                    cfg.llm.backend_type = backend
                    cfg.llm.openclaw_port = int(oc_port)
                    cfg.llm.openclaw_model = oc_model
                    cfg.llm.auto_fallback = fallback
                    cfg.save()
                    # Reset LLM client singleton
                    from services.llm_client import LLMClient
                    LLMClient._instance = None
                    return "Da luu cai dat!"

                save_btn.click(
                    fn=save_settings,
                    inputs=[api_key, base_url, model_name, temperature, max_tokens,
                            backend_type, openclaw_port, openclaw_model, auto_fallback],
                    outputs=[save_status],
                )

            # ═══════════════════════════════════════
            # TAB 3: HƯỚNG DẪN
            # ═══════════════════════════════════════
            with gr.TabItem("Hướng Dẫn"):
                gr.Markdown("""
                ## Hướng dẫn sử dụng Novel Auto Pipeline

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
