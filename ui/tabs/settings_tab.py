"""Settings tab — API config, web auth, cache management, language, compact mode."""

import logging
import threading
import gradio as gr
from config import ConfigManager, PIPELINE_PRESETS

_log = logging.getLogger(__name__)

_DEPRECATION_MSG = (
    "BrowserAuth (browser-based credential capture) is deprecated and will be "
    "removed in v4.0. Use API key authentication (STORYFORGE_API_KEY) instead."
)


def _get_browser_auth():
    """Import BrowserAuth with deprecation warning. Raises on failure."""
    _log.warning(_DEPRECATION_MSG)
    from services.browser_auth import BrowserAuth
    return BrowserAuth()


# ── Web auth helpers (thin wrappers, kept here to avoid circular deps) ──
# NOTE: BrowserAuth is deprecated. These helpers remain for backward compatibility
# but emit a deprecation warning. Use STORYFORGE_API_KEY env var instead.

def _launch_chrome(_t):
    try:
        _, msg = _get_browser_auth().launch_chrome()
    except Exception as exc:
        return f"Browser auth unavailable: {exc}"
    return msg


def _capture_credentials(_t):
    try:
        auth = _get_browser_auth()
    except Exception as exc:
        yield f"Browser auth unavailable: {exc}"
        return
    result = [None]
    threading.Thread(target=lambda: result.__setitem__(0, auth.capture_deepseek_credentials(timeout=300))).start()
    yield _t("settings.waiting_login")
    import time as _time
    while result[0] is None:
        _time.sleep(2)
        if auth.is_authenticated():
            break
        yield _t("settings.waiting_login")
    if result[0]:
        _, msg = result[0]
        yield msg
    else:
        yield _t("settings.login_timeout")


def _clear_credentials(_t):
    try:
        _get_browser_auth().clear_credentials()
    except Exception as exc:
        return f"Browser auth unavailable: {exc}"
    return _t("settings.creds_cleared")


def _check_auth_status(_t):
    try:
        auth = _get_browser_auth()
    except Exception:
        return _t("settings.not_logged_in")
    if auth.is_authenticated():
        creds = auth.get_credentials()
        return _t("settings.logged_in", time=(creds or {}).get("updated_at", "?"))
    return _t("settings.not_logged_in")


# ── Tab builder ──

def build_settings_tab(_t, i18n, app_block):
    """Build the settings and configuration tab.

    Args:
        _t: i18n translation callable
        i18n: I18n singleton instance
        app_block: the top-level gr.Blocks instance (for compact mode + load hook)

    Returns:
        dict with language_selector and save_status component refs.
    """
    from services.i18n import SUPPORTED_LANGUAGES
    config = ConfigManager()

    # ── General Settings ──
    with gr.Accordion(_t("label.language") + " & Display", open=True):
        lang_choices = [f"{v} ({k})" for k, v in SUPPORTED_LANGUAGES.items()]
        language_selector = gr.Dropdown(
            choices=lang_choices,
            value=f"{SUPPORTED_LANGUAGES.get(i18n.lang, 'vi')} ({i18n.lang})",
            label=_t("label.language"), info=_t("settings.language_restart"),
        )
        compact_mode_cb = gr.Checkbox(
            value=False,
            label=_t("settings.compact_mode") if _t("settings.compact_mode") != "settings.compact_mode" else "Compact Mode",
            info="Reduce padding and font size for smaller screens",
        )
        compact_mode_cb.change(
            fn=lambda e: gr.update(elem_classes=["compact-mode"] if e else []),
            inputs=[compact_mode_cb], outputs=[app_block],
        )

    # ── Pipeline Presets ──
    with gr.Accordion("Cài đặt nhanh (Presets)", open=False):
        _preset_choices = [f"{v['label']} ({k})" for k, v in PIPELINE_PRESETS.items()]
        preset_dropdown = gr.Dropdown(
            choices=["Tùy chỉnh"] + _preset_choices,
            value="Tùy chỉnh",
            label="Chế độ cài đặt",
            info="Chọn preset để tự động cấu hình các tính năng",
        )
        apply_preset_btn = gr.Button("Áp dụng preset", size="sm")
        preset_status = gr.Textbox(label="Trạng thái preset", interactive=False, visible=False)

    # ── API Configuration ──
    with gr.Accordion(_t("settings.api_config"), open=True):
        api_key = gr.Textbox(label=_t("settings.api_key"), value=config.llm.api_key, type="password")
        base_url = gr.Textbox(label=_t("settings.base_url"), value=config.llm.base_url)
        model_name = gr.Textbox(label=_t("settings.model"), value=config.llm.model)
        with gr.Row():
            temperature = gr.Slider(0, 2, value=config.llm.temperature, step=0.1, label=_t("settings.temperature"))
            max_tokens = gr.Slider(1024, 16384, value=config.llm.max_tokens, step=512, label=_t("settings.max_tokens"))

    # ── Cheap Model ──
    with gr.Accordion(_t("settings.cheap_model"), open=False):
        cheap_model = gr.Textbox(label=_t("settings.cheap_model_label"), value=config.llm.cheap_model, placeholder=_t("settings.cheap_model_placeholder"))
        cheap_base_url = gr.Textbox(label=_t("settings.cheap_url_label"), value=config.llm.cheap_base_url, placeholder=_t("settings.cheap_url_placeholder"))

    # ── Backend ──
    with gr.Accordion(_t("settings.backend"), open=False):
        backend_type = gr.Radio(choices=["api", "web"], value=config.llm.backend_type, label=_t("settings.backend_label"), info=_t("settings.backend_info"))

        # Web auth
        gr.Markdown(_t("settings.web_auth"))
        web_auth_status = gr.Textbox(label=_t("settings.auth_status"), interactive=False, value=_t("settings.not_logged_in"))
        with gr.Row():
            launch_chrome_btn = gr.Button(_t("btn.launch_chrome"), size="sm")
            capture_btn = gr.Button(_t("btn.capture_creds"), variant="primary", size="sm")
        clear_auth_btn = gr.Button(_t("btn.clear_creds"), variant="stop", size="sm")
        launch_chrome_btn.click(fn=lambda: _launch_chrome(_t), outputs=[web_auth_status])
        capture_btn.click(fn=lambda: _capture_credentials(_t), outputs=[web_auth_status])
        clear_auth_btn.click(fn=lambda: _clear_credentials(_t), outputs=[web_auth_status])
        app_block.load(fn=lambda: _check_auth_status(_t), outputs=[web_auth_status])

    # ── Connection Test ──
    with gr.Row():
        connection_status = gr.Textbox(label=_t("settings.connection_status"), interactive=False, scale=3)
        test_connection_btn = gr.Button(_t("btn.test_connection"), scale=1)

    def test_connection(backend, key, url, model):
        cfg = ConfigManager()
        cfg.llm.backend_type = backend
        if backend == "api":
            cfg.llm.api_key, cfg.llm.base_url, cfg.llm.model = key, url, model
        from services.llm_client import LLMClient
        LLMClient._instance = None
        ok, msg = LLMClient().check_connection()
        return f"{'OK' if ok else 'LỖI'}: {msg}"

    test_connection_btn.click(fn=test_connection, inputs=[backend_type, api_key, base_url, model_name], outputs=[connection_status])

    # ── Cache Management ──
    with gr.Accordion(_t("settings.cache_title"), open=False):
        cache_info = gr.Textbox(label=_t("settings.cache_label"), interactive=False)
        with gr.Row():
            cache_stats_btn = gr.Button(_t("btn.cache_stats"), size="sm")
            cache_clear_btn = gr.Button(_t("btn.clear_cache"), variant="stop", size="sm")

        def show_cache_stats():
            try:
                from services.llm_cache import LLMCache
                s = LLMCache(ttl_days=ConfigManager().llm.cache_ttl_days).stats()
                return f"Total: {s['total']} | Valid: {s['valid']} | Expired: {s['expired']}"
            except Exception as e:
                return f"Lỗi: {e}"

        def clear_cache():
            try:
                from services.llm_cache import LLMCache
                LLMCache().clear()
                return "Đã xóa cache!"
            except Exception as e:
                return f"Lỗi: {e}"

        cache_stats_btn.click(fn=show_cache_stats, outputs=[cache_info])
        cache_clear_btn.click(fn=clear_cache, outputs=[cache_info])

    # ── Self-review settings ──
    with gr.Accordion(_t("settings.self_review_title"), open=False):
        enable_self_review_cb = gr.Checkbox(
            value=config.pipeline.enable_self_review,
            label=_t("label.self_review_enable"),
        )
        self_review_threshold = gr.Slider(
            1.0, 5.0, value=config.pipeline.self_review_threshold,
            step=0.5, label=_t("label.self_review_threshold"),
            info=_t("settings.self_review_threshold_info"),
        )

    # Preset apply handler
    def apply_preset(choice):
        if not choice or choice == "Tùy chỉnh":
            return gr.update(), gr.update(), gr.update(value="Không có thay đổi.", visible=True)
        key = choice.split("(")[-1].rstrip(")")
        preset = PIPELINE_PRESETS.get(key)
        if not preset:
            return gr.update(), gr.update(), gr.update(value=f"Preset '{key}' không tồn tại.", visible=True)
        cfg = ConfigManager()
        for field_name, value in preset.items():
            if field_name == "label":
                continue
            if hasattr(cfg.pipeline, field_name):
                setattr(cfg.pipeline, field_name, value)
        cfg.save()
        return (
            gr.update(value=preset.get("enable_self_review", False)),
            gr.update(value=preset.get("self_review_threshold", 3.0)),
            gr.update(value=f"Đã áp dụng preset: {preset['label']}", visible=True),
        )

    apply_preset_btn.click(
        fn=apply_preset,
        inputs=[preset_dropdown],
        outputs=[enable_self_review_cb, self_review_threshold, preset_status],
    )

    # Save settings
    save_btn = gr.Button(_t("btn.save_settings"), variant="primary")
    save_status = gr.Textbox(label=_t("settings.status_label"), interactive=False)

    def save_settings(key, url, model, temp, tokens, cheap_m, cheap_url, backend, lang_choice,
                      self_review_enabled, self_review_thresh):
        cfg = ConfigManager()
        cfg.llm.api_key, cfg.llm.base_url, cfg.llm.model = key, url, model
        cfg.llm.temperature, cfg.llm.max_tokens = temp, int(tokens)
        cfg.llm.cheap_model, cfg.llm.cheap_base_url, cfg.llm.backend_type = cheap_m, cheap_url, backend
        if lang_choice:
            lang_code = lang_choice.split("(")[-1].rstrip(")")
            cfg.pipeline.language = lang_code
            i18n.set_language(lang_code)
        cfg.pipeline.enable_self_review = self_review_enabled
        cfg.pipeline.self_review_threshold = self_review_thresh
        cfg.save()
        from services.llm_client import LLMClient
        LLMClient._instance = None
        return _t("settings.saved")

    save_btn.click(
        fn=save_settings,
        inputs=[api_key, base_url, model_name, temperature, max_tokens,
                cheap_model, cheap_base_url, backend_type, language_selector,
                enable_self_review_cb, self_review_threshold],
        outputs=[save_status],
    )

    return {"language_selector": language_selector, "save_status": save_status}
