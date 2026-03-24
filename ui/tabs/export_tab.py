"""Export tab — PDF, TTS, audio, and share story export."""

import gradio as gr
from ui.handlers import (
    handle_export_pdf,
    handle_export_tts,
    handle_export_tts_audio,
    handle_share_story,
)


def build_export_tab(_t, orchestrator_state):
    """Build the export tab (PDF, TTS script, TTS audio, share).

    Args:
        _t: i18n translation callable
        orchestrator_state: gr.State holding the PipelineOrchestrator instance

    Returns:
        dict of components (none need external wiring — handlers registered here).
    """
    gr.Markdown(f"### {_t('tab.export')}")
    with gr.Row():
        pdf_btn = gr.Button(_t("btn.export_pdf"), variant="secondary")
        tts_btn = gr.Button(_t("btn.export_tts"), variant="secondary")
        share_btn = gr.Button(_t("btn.share"), variant="primary")

    gr.Markdown("---")
    gr.Markdown(f"#### {_t('label.voice_select')}")
    with gr.Row():
        voice_selector = gr.Dropdown(
            choices=["female", "male"],
            value="female",
            label=_t("label.voice_select"),
            info=f"{_t('voice_female')} / {_t('voice_male')}",
        )
        audio_btn = gr.Button(_t("btn.export_audio"), variant="secondary")

    audio_status = gr.Textbox(label="Status", interactive=False, visible=True)
    export_file_output = gr.File(label="Download", file_count="multiple")
    share_link_display = gr.Textbox(label=_t("label.share_link"), interactive=False)
    reading_stats_display = gr.JSON(label=_t("label.reading_stats"))

    def _export_pdf(orch_state):
        return handle_export_pdf(orch_state, _t)

    def _export_tts(orch_state):
        return handle_export_tts(orch_state, _t)

    def _export_audio(orch_state, voice):
        paths, msg = handle_export_tts_audio(orch_state, voice=voice)
        return paths, msg

    def _share_story(orch_state):
        return handle_share_story(orch_state, _t)

    pdf_btn.click(
        fn=_export_pdf,
        inputs=[orchestrator_state],
        outputs=[export_file_output, reading_stats_display],
    )
    tts_btn.click(
        fn=_export_tts,
        inputs=[orchestrator_state],
        outputs=[export_file_output],
    )
    audio_btn.click(
        fn=_export_audio,
        inputs=[orchestrator_state, voice_selector],
        outputs=[export_file_output, audio_status],
    )
    share_btn.click(
        fn=_share_story,
        inputs=[orchestrator_state],
        outputs=[share_link_display, export_file_output],
    )

    return {
        "export_file_output": export_file_output,
        "share_link_display": share_link_display,
        "reading_stats_display": reading_stats_display,
        "audio_status": audio_status,
    }
