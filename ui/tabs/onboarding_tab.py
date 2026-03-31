"""Onboarding wizard tab — guided first-time user experience."""

import gradio as gr
from services.onboarding import OnboardingManager, STEPS


def build_onboarding_banner(_t):
    """Build onboarding wizard banner shown at top of main UI.

    Returns dict with component refs for wiring.
    """
    mgr = OnboardingManager()

    # Only show if not completed
    visible = not mgr.is_completed
    step = mgr.get_current_step_info()

    with gr.Group(visible=visible, elem_classes=["onboarding-banner"]) as onboarding_group:
        gr.Markdown("### Hướng dẫn bắt đầu")
        step_title = gr.Markdown(f"**{step['title']}**")
        step_desc = gr.Markdown(step["description"])

        with gr.Row():
            next_btn = gr.Button("Tiếp theo ->", variant="primary", size="sm")
            skip_btn = gr.Button("Bỏ qua", variant="secondary", size="sm")

    def on_next():
        m = OnboardingManager()
        info = m.advance()
        if m.is_completed:
            return (
                gr.update(visible=False),
                gr.update(value=f"**{info['title']}**"),
                gr.update(value=info["description"]),
            )
        return (
            gr.update(visible=True),
            gr.update(value=f"**{info['title']}**"),
            gr.update(value=info["description"]),
        )

    def on_skip():
        OnboardingManager().skip()
        return (
            gr.update(visible=False),
            gr.update(),
            gr.update(),
        )

    next_btn.click(fn=on_next, outputs=[onboarding_group, step_title, step_desc])
    skip_btn.click(fn=on_skip, outputs=[onboarding_group, step_title, step_desc])

    return {
        "onboarding_group": onboarding_group,
        "step_title": step_title,
        "step_desc": step_desc,
    }
