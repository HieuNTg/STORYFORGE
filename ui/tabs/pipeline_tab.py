"""Pipeline tab — story input form and run button."""

import gradio as gr


def build_pipeline_tab(_t, _genres, _styles, _drama_levels):
    """Build the left-column pipeline input form.

    Args:
        _t: i18n translation callable
        _genres: callable returning list of genre strings
        _styles: callable returning list of style strings
        _drama_levels: callable returning list of drama level strings

    Returns:
        dict of Gradio component references needed for wiring handlers.
    """
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

    return {
        "genre_input": genre_input,
        "template_dropdown": template_dropdown,
        "quick_start_btn": quick_start_btn,
        "title_input": title_input,
        "style_input": style_input,
        "idea_input": idea_input,
        "num_chapters": num_chapters,
        "num_characters": num_characters,
        "word_count": word_count,
        "sim_rounds": sim_rounds,
        "drama_level": drama_level,
        "shots_per_ch": shots_per_ch,
        "enable_agents_cb": enable_agents_cb,
        "enable_scoring_cb": enable_scoring_cb,
        "run_btn": run_btn,
    }
