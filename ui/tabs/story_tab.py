"""Story tab — draft and enhanced output display."""

import gradio as gr


def build_story_tab(_t):
    """Build the story output tab (Layer 1 draft + Layer 2 enhanced).

    Args:
        _t: i18n translation callable

    Returns:
        dict with draft_output and enhanced_output components.
    """
    gr.Markdown(_t("output.draft_header"))
    draft_output = gr.Textbox(
        label=_t("label.draft"), lines=15, interactive=False,
    )
    gr.Markdown(_t("output.enhanced_header"))
    enhanced_output = gr.Textbox(
        label=_t("label.enhanced"), lines=15,
        interactive=False,
    )

    return {
        "draft_output": draft_output,
        "enhanced_output": enhanced_output,
    }
