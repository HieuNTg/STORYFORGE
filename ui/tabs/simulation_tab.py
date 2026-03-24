"""Simulation tab — simulation results and escalation events display."""

import gradio as gr


def build_simulation_tab(_t):
    """Build the simulation results tab.

    Args:
        _t: i18n translation callable

    Returns:
        dict with sim_output and escalation_display components.
    """
    sim_output = gr.Textbox(
        label=_t("label.sim_result"), lines=20,
        interactive=False,
    )
    with gr.Accordion(_t("label.escalation"), open=False):
        escalation_display = gr.JSON(label=_t("label.escalation"))

    return {
        "sim_output": sim_output,
        "escalation_display": escalation_display,
    }
