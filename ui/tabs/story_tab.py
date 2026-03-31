"""Story tab — draft and enhanced output display."""

import gradio as gr


def build_story_tab(_t):
    """Build the story output tab (Layer 1 draft + Layer 2 enhanced).

    Args:
        _t: i18n translation callable

    Returns:
        dict with draft_output and enhanced_output components.
    """
    with gr.Accordion(_t("output.draft_header"), open=True):
        draft_output = gr.Textbox(
            label=_t("label.draft"), lines=15, interactive=False,
            elem_classes=["output-panel"],
        )
    with gr.Accordion(_t("output.enhanced_header"), open=True):
        enhanced_output = gr.Textbox(
            label=_t("label.enhanced"), lines=15,
            interactive=False,
            elem_classes=["output-panel"],
        )

    return {
        "draft_output": draft_output,
        "enhanced_output": enhanced_output,
    }
