"""Account tab — login, register, and story library."""

import gradio as gr
from ui.handlers import handle_login, handle_register, handle_save_story
from services.credit_manager import TIER_LIMITS


def _build_usage_summary(profile_dict: dict, _t) -> str:
    """Format usage summary markdown from profile dict."""
    if not profile_dict:
        return ""
    tier = profile_dict.get("tier", "free")
    credits = profile_dict.get("credits", 0)
    stories = profile_dict.get("total_stories_created", 0)
    usage = profile_dict.get("usage_count", 0)
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    monthly = limits["monthly_credits"]
    max_ch = limits["max_chapters"]

    tier_labels = {"free": _t("tier_free"), "pro": _t("tier_pro"), "studio": _t("tier_studio")}
    tier_label = tier_labels.get(tier, tier)

    monthly_str = "∞" if monthly == -1 else str(monthly)
    max_ch_str = "∞" if max_ch == -1 else str(max_ch)

    return (
        f"**{_t('label_tier')}:** {tier_label}  \n"
        f"**{_t('label_credits')}:** {credits} / {monthly_str}  \n"
        f"**{_t('label_usage_summary')}:** {stories} truyện đã tạo | {usage} lần sử dụng  \n"
        f"**Giới hạn chương:** {max_ch_str}"
    )


def build_account_tab(_t, orchestrator_state, user_state=None):
    """Build the account management tab.

    Args:
        _t: i18n translation callable
        orchestrator_state: gr.State holding the PipelineOrchestrator instance
        user_state: optional external gr.State for user profile dict (shared with pipeline tab)

    Returns:
        dict with user_state and other components.
    """
    gr.Markdown(f"### {_t('tab.account')}")
    if user_state is None:
        user_state = gr.State(value=None)
    with gr.Row():
        username_input = gr.Textbox(label=_t("label.username"), scale=1)
        password_input = gr.Textbox(
            label=_t("label.password"), type="password", scale=1,
        )
    with gr.Row():
        login_btn = gr.Button(_t("btn.login"), variant="primary")
        register_btn = gr.Button(_t("btn.register"), variant="secondary")
    login_status = gr.Textbox(label="Status", interactive=False)

    # Usage summary display (credits + tier info)
    usage_summary = gr.Markdown(value="", label=_t("label_usage_summary"))

    gr.Markdown(f"### {_t('label.story_library')}")
    story_library_display = gr.Dataframe(
        headers=["ID", "Title", "Date"],
        label=_t("label.story_library"),
        interactive=False,
    )
    with gr.Row():
        save_title_input = gr.Textbox(
            label=_t("label.title"), placeholder="Story title",
        )
        save_story_btn = gr.Button(_t("btn.save_story"), variant="secondary")
    save_story_status = gr.Textbox(label="Status", interactive=False)

    def _login(username, password):
        result = handle_login(username, password, _t)
        profile_dict = result[0]
        summary = _build_usage_summary(profile_dict, _t)
        return result + (summary,)

    def _register(username, password):
        result = handle_register(username, password, _t)
        profile_dict = result[0]
        summary = _build_usage_summary(profile_dict, _t)
        return result + (summary,)

    def _save_story(user_st, orch_state, title):
        return handle_save_story(user_st, orch_state, title, _t)

    login_btn.click(
        fn=_login,
        inputs=[username_input, password_input],
        outputs=[user_state, login_status, story_library_display, usage_summary],
    )
    register_btn.click(
        fn=_register,
        inputs=[username_input, password_input],
        outputs=[user_state, login_status, story_library_display, usage_summary],
    )
    save_story_btn.click(
        fn=_save_story,
        inputs=[user_state, orchestrator_state, save_title_input],
        outputs=[save_story_status, story_library_display],
    )

    return {
        "user_state": user_state,
        "story_library_display": story_library_display,
    }
