"""Reader tab — embedded web story reader with progress tracking."""
import gradio as gr
import logging

logger = logging.getLogger(__name__)


def build_reader_tab(_t, orchestrator_state):
    """Build the web reader tab.

    Args:
        _t: i18n translation callable
        orchestrator_state: gr.State holding the PipelineOrchestrator

    Returns:
        dict of components.
    """
    gr.Markdown(_t("reader.title"))

    with gr.Row():
        load_btn = gr.Button(_t("reader.open_btn"), variant="primary")
        gr.Button(_t("reader.new_window_btn"), variant="secondary")

    reader_html = gr.HTML(
        value=f"<div style='text-align:center;padding:60px;color:#888'>{_t('reader.placeholder')}</div>",
        label="Story Reader",
    )
    reader_file = gr.File(label="Download HTML Reader", visible=False)

    def _load_reader(orch_state):
        if orch_state is None:
            return (
                f"<div style='text-align:center;padding:60px;color:#e74c3c'>"
                f"{_t('reader.no_story')}</div>",
                None,
            )
        try:
            from services.web_reader_generator import WebReaderGenerator
            story = (
                orch_state.output.enhanced_story
                or orch_state.output.story_draft
            )
            if not story or not story.chapters:
                return (
                    f"<div style='text-align:center;padding:60px;color:#e74c3c'>"
                    f"{_t('reader.no_content')}</div>",
                    None,
                )
            chars = (
                orch_state.output.story_draft.characters
                if orch_state.output.story_draft
                else []
            )
            html_content = WebReaderGenerator.generate(story, characters=chars)

            # Save to file for download / new-window access
            import os
            import glob
            os.makedirs("output", exist_ok=True)
            # Clean up stale reader files before writing new one
            for old_file in glob.glob(os.path.join("output", "web_reader*.html")):
                try:
                    os.remove(old_file)
                except OSError:
                    pass
            reader_path = "output/web_reader.html"
            with open(reader_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Embed HTML content directly via srcdoc to avoid file:// protocol
            # restrictions in Chrome and other browsers.
            import html as _html
            escaped = _html.escape(html_content, quote=True)
            iframe_html = (
                f'<iframe srcdoc="{escaped}" '
                f'style="width:100%;height:80vh;border:1px solid #ddd;border-radius:8px" '
                f'sandbox="allow-scripts"></iframe>'
            )
            return iframe_html, reader_path
        except Exception as e:
            logger.error(f"Reader error: {e}")
            return f"<div style='color:red'>Lỗi: {e}</div>", None

    load_btn.click(
        fn=_load_reader,
        inputs=[orchestrator_state],
        outputs=[reader_html, reader_file],
    )

    return {
        "reader_html": reader_html,
        "reader_file": reader_file,
    }
