"""Review tab — agent reviews and quality scores display."""

import gradio as gr


def build_review_tab(_t):
    """Build the agent review and quality scores tab.

    Args:
        _t: i18n translation callable

    Returns:
        dict with agent_output and quality_output components.
    """
    with gr.Accordion(_t("label.agent_result"), open=True):
        agent_output = gr.Textbox(
            label=_t("label.agent_result"), lines=12,
            interactive=False,
            elem_classes=["output-panel"],
        )
    with gr.Accordion("Quality Scores", open=True):
        quality_output = gr.Markdown(
            value=_t("output.no_quality"),
        )

    return {
        "agent_output": agent_output,
        "quality_output": quality_output,
    }
