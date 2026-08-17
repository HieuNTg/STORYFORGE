"""Config API routes — settings CRUD, connection test, cache management.

RBAC examples
-------------
These routes touch pipeline configuration and should be protected in production.
Import the helpers from middleware.rbac and add them as Depends():

    from fastapi import Depends
    from middleware.rbac import require_permission, require_role, Permission, Role

    # Require CONFIGURE_PIPELINE permission (admin + superadmin):
    # @router.put("", dependencies=[Depends(require_permission(Permission.CONFIGURE_PIPELINE))])

    # Require at least ADMIN role (coarser check):
    # @router.put("", dependencies=[Depends(require_role(Role.ADMIN))])

    # Inject user for handler-level logic (e.g., audit who changed config):
    # @router.put("")
    # def save_config(body: ConfigUpdate, user=Depends(require_permission(Permission.CONFIGURE_PIPELINE))):
    #     logger.info("Config updated by %r", user["user_id"])
    #     ...

    # Restrict API key management to SUPERADMIN only:
    # @router.get("/api-keys", dependencies=[Depends(require_permission(Permission.MANAGE_API_KEYS))])

    # Restrict audit log access to SUPERADMIN only:
    # @router.get("/audit", dependencies=[Depends(require_permission(Permission.VIEW_AUDIT_LOGS))])

    # Restrict user management endpoints to ADMIN+:
    # @router.get("/admin/users", dependencies=[Depends(require_permission(Permission.MANAGE_USERS))])

    # Restrict analytics to ADMIN+:
    # @router.get("/analytics", dependencies=[Depends(require_permission(Permission.ACCESS_ANALYTICS))])
"""

import logging
import re
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from typing import Optional

from config import ConfigManager, PIPELINE_PRESETS, PROVIDER_PRESETS
from middleware.rbac import Permission, require_permission_if_enabled
from services.i18n import I18n, SUPPORTED_LANGUAGES
from services.security.url_validator import validate_base_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["config"])


def _mask_key(k: str) -> str:
    """Mask an API key for display — show first 6 and last 4 chars."""
    if not k:
        return ""
    return k[:6] + "***" + k[-4:] if len(k) > 10 else "***"


def _detect_provider_name(base_url: str) -> str:
    """Auto-detect provider name from base_url."""
    url = (base_url or "").lower()
    if "openai.com" in url:
        return "openai"
    if "googleapis.com" in url or "generativelanguage" in url:
        return "gemini"
    if "anthropic.com" in url:
        return "anthropic"
    if "openrouter.ai" in url:
        return "openrouter"
    if "kymaapi.com" in url:
        return "kyma"
    if "z.ai" in url:
        return "zai"
    if "localhost" in url or "127.0.0.1" in url:
        return "local"
    return "custom"


PROVIDER_FROM_KEY = [
    (
        "sk-ant-",
        {
            "name": "Anthropic",
            "base_url": "https://api.anthropic.com/v1/",
            "model": "claude-haiku-4-5-20251001",
        },
    ),
    (
        "sk-or-",
        {
            "name": "OpenRouter",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "qwen/qwen3.6-plus:free",
        },
    ),
    (
        "sk-proj-",
        {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
    ),
    (
        "sk-",
        {
            "name": "OpenAI",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
    ),
    (
        "AIza",
        {
            "name": "Google Gemini",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "model": "gemini-2.5-flash",
        },
    ),
    (
        "ky-",
        {
            "name": "Kyma",
            "base_url": "https://kymaapi.com/v1",
            "model": "qwen-3.6-plus",
        },
    ),
    (
        "kyma-",
        {
            "name": "Kyma",
            "base_url": "https://kymaapi.com/v1",
            "model": "qwen-3.6-plus",
        },
    ),
]


def _detect_provider_from_key(api_key: str) -> dict | None:
    """Auto-detect provider config from API key prefix."""
    for prefix, config in PROVIDER_FROM_KEY:
        if api_key.startswith(prefix):
            return config
    # Z.AI keys: 32 hex chars + dot + alphanumeric (e.g., 1e8d5fd...951.ee3dhU4x...)
    if re.match(r"^[a-f0-9]{32}\.[A-Za-z0-9]+$", api_key):
        return {
            "name": "Z.AI",
            "base_url": "https://api.z.ai/api/paas/v4",
            "model": "glm-4.7-flash",
        }
    return None


class ProfileCreate(BaseModel):
    """Request body for creating/updating an API profile."""

    name: str = ""
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    enabled: bool = True


class ConfigUpdate(BaseModel):
    """Request body for saving settings."""

    api_key: Optional[str] = None
    api_keys: Optional[list] = None
    append_api_keys: Optional[list] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    cheap_model: Optional[str] = None
    cheap_base_url: Optional[str] = None
    language: Optional[str] = None
    layer1_model: Optional[str] = None
    layer2_model: Optional[str] = None
    enable_self_review: Optional[bool] = None
    self_review_threshold: Optional[float] = None
    image_provider: Optional[str] = None
    codex_model: Optional[str] = None
    hf_token: Optional[str] = None
    hf_image_model: Optional[str] = None
    image_prompt_style: Optional[str] = None
    # Feature toggles (PipelineConfig flags exposed in Settings UI)
    enable_drama_climax: Optional[bool] = None
    enable_pipeline_overlay: Optional[bool] = None
    enable_chapter_illustration: Optional[bool] = None
    enable_simulation_transcript: Optional[bool] = None
    # FlowKit (Chrome Extension + Google Labs proxy)
    flowkit_enabled: Optional[bool] = None
    flowkit_port: Optional[int] = None
    flowkit_style_reference_path: Optional[str] = None
    flowkit_concurrent_workers_max: Optional[int] = None
    flowkit_workers_ramp_threshold: Optional[int] = None
    flowkit_veo_poll_interval: Optional[float] = None
    flowkit_account_warning_shown: Optional[bool] = None
    flowkit_risk_acknowledged: Optional[bool] = None
    flowkit_image_input_type_split: Optional[bool] = None
    flowkit_callback_hmac_required: Optional[bool] = None
    flowkit_use_refiner: Optional[bool] = None
    flowkit_request_timeout: Optional[float] = None
    flowkit_aspect_ratio: Optional[str] = None
    flowkit_project_id: Optional[str] = None


_CONFIGURE_PIPELINE = Depends(
    require_permission_if_enabled(Permission.CONFIGURE_PIPELINE)
)
_MANAGE_API_KEYS = Depends(require_permission_if_enabled(Permission.MANAGE_API_KEYS))


# Mask-shape regex: matches the masked echo emitted by `_mask_key` and the
# primary api_key mask (e.g. `sk-12***abcd`, `***abcd`, `abc***xyz`). Used to
# reject PUT bodies that round-trip the masked echo as a "new" key (F5).
_MASKED_KEY_RE = re.compile(r"^.{0,8}\*{2,}.{0,8}$")


def _is_masked_echo(value: Optional[str]) -> bool:
    """Return True if `value` looks like a masked echo (`abc***xyz` or `***abcd`)."""
    if not value or not isinstance(value, str):
        return False
    return bool(_MASKED_KEY_RE.match(value))


@router.get("", dependencies=[_CONFIGURE_PIPELINE])
def get_config(response: Response):
    """Return current config (API key and HF token masked).

    `Cache-Control: no-store, private` is set as defense-in-depth (F17): the
    response carries masked secrets today, but we never want a service-worker,
    proxy, or browser cache holding a copy in case of future regressions.
    """
    response.headers["Cache-Control"] = "no-store, private"
    cfg = ConfigManager()
    key = cfg.llm.api_key or ""
    masked_key = key[:4] + "***" + key[-4:] if len(key) > 8 else "***"
    hf_tok = cfg.pipeline.hf_token or ""
    masked_hf_token = (
        "***" + hf_tok[-4:] if len(hf_tok) > 4 else ("***" if hf_tok else "")
    )
    profiles_masked = []
    for fb in cfg.llm.fallback_models:
        profiles_masked.append(
            {
                "name": fb.get("name", fb.get("model", "Unknown")),
                "provider": _detect_provider_name(fb.get("base_url", "")),
                "base_url": fb.get("base_url", ""),
                "api_key_masked": _mask_key(fb.get("api_key", "")),
                "model": fb.get("model", ""),
                "enabled": fb.get("enabled", True),
                "last_test_ok": fb.get("last_test_ok"),
                "last_tested_at": fb.get("last_tested_at", ""),
                "last_test_message": fb.get("last_test_message", ""),
            }
        )
    return {
        "llm": {
            "api_key_masked": masked_key,
            "base_url": cfg.llm.base_url,
            "model": cfg.llm.model,
            "temperature": cfg.llm.temperature,
            "max_tokens": cfg.llm.max_tokens,
            "cheap_model": cfg.llm.cheap_model,
            "cheap_base_url": cfg.llm.cheap_base_url,
            "api_keys_masked": [
                _mask_key(k)
                for raw in cfg.llm.api_keys
                for k in [
                    raw
                    if isinstance(raw, str)
                    else (raw.get("key") or raw.get("api_key") or "")
                ]
                if k
            ],
            "api_keys_count": len(cfg.llm.api_keys),
            "profiles": profiles_masked,
            "layer1_model": cfg.llm.layer1_model,
            "layer2_model": cfg.llm.layer2_model,
        },
        "pipeline": {
            "language": cfg.pipeline.language,
            "enable_self_review": cfg.pipeline.enable_self_review,
            "self_review_threshold": cfg.pipeline.self_review_threshold,
            "image_provider": cfg.pipeline.image_provider,
            "codex_model": getattr(cfg.pipeline, "codex_model", ""),
            "hf_token_masked": masked_hf_token,
            "hf_image_model": cfg.pipeline.hf_image_model,
            "image_prompt_style": cfg.pipeline.image_prompt_style,
            "enable_simulation_transcript": getattr(
                cfg.pipeline, "enable_simulation_transcript", False
            ),
            "enable_drama_climax": getattr(cfg.pipeline, "enable_drama_climax", False),
            "enable_pipeline_overlay": getattr(
                cfg.pipeline, "enable_pipeline_overlay", False
            ),
            "enable_chapter_illustration": getattr(
                cfg.pipeline, "enable_chapter_illustration", False
            ),
            "flowkit_enabled": cfg.pipeline.flowkit_enabled,
            "flowkit_port": cfg.pipeline.flowkit_port,
            "flowkit_style_reference_path": cfg.pipeline.flowkit_style_reference_path,
            "flowkit_concurrent_workers": cfg.pipeline.flowkit_concurrent_workers,
            "flowkit_concurrent_workers_max": cfg.pipeline.flowkit_concurrent_workers_max,
            "flowkit_workers_ramp_threshold": cfg.pipeline.flowkit_workers_ramp_threshold,
            "flowkit_veo_poll_interval": cfg.pipeline.flowkit_veo_poll_interval,
            "flowkit_account_warning_shown": cfg.pipeline.flowkit_account_warning_shown,
            "flowkit_risk_acknowledged": cfg.pipeline.flowkit_risk_acknowledged,
            "flowkit_image_input_type_split": cfg.pipeline.flowkit_image_input_type_split,
            "flowkit_callback_hmac_required": cfg.pipeline.flowkit_callback_hmac_required,
            "flowkit_use_refiner": cfg.pipeline.flowkit_use_refiner,
            "flowkit_request_timeout": cfg.pipeline.flowkit_request_timeout,
            "flowkit_aspect_ratio": cfg.pipeline.flowkit_aspect_ratio,
            "flowkit_project_id": cfg.pipeline.flowkit_project_id,
        },
    }


@router.put("", dependencies=[_CONFIGURE_PIPELINE])
def save_config(body: ConfigUpdate):
    """Save settings to config.json."""
    # FlowKit hard gate: enabling the provider requires explicit risk
    # acknowledgement. Evaluated against the post-PATCH effective state
    # (delta + current) so a previously-acked user can toggle enabled alone.
    cfg = ConfigManager()
    eff_provider = (
        body.image_provider
        if body.image_provider is not None
        else cfg.pipeline.image_provider
    )
    eff_enabled = (
        body.flowkit_enabled
        if body.flowkit_enabled is not None
        else cfg.pipeline.flowkit_enabled
    )
    eff_ack = (
        body.flowkit_risk_acknowledged
        if body.flowkit_risk_acknowledged is not None
        else cfg.pipeline.flowkit_risk_acknowledged
    )
    if eff_provider == "flowkit" and eff_enabled and not eff_ack:
        raise HTTPException(
            status_code=400,
            detail="flowkit_risk_acknowledged required when enabling flowkit",
        )

    # F5 guard: reject mask-shaped values for any secret field. A correctly-
    # behaving frontend uses delta-only PUT and never sends the masked echo
    # back. This catches the regression where a bug echoes `sk-***1234` as
    # the new key, which would otherwise overwrite the real key with the mask.
    for field_name in ("api_key", "hf_token"):
        if _is_masked_echo(getattr(body, field_name, None)):
            raise HTTPException(
                status_code=400,
                detail=f"masked echo cannot be persisted as a real {field_name}",
            )
    if body.api_keys is not None:
        for k in body.api_keys:
            key_value = (
                k
                if isinstance(k, str)
                else (k or {}).get("key") or (k or {}).get("api_key")
            )
            if _is_masked_echo(key_value):
                raise HTTPException(
                    status_code=400,
                    detail="masked echo cannot be persisted as a real api_keys entry",
                )
    if body.append_api_keys:
        for k in body.append_api_keys:
            if _is_masked_echo(k if isinstance(k, str) else None):
                raise HTTPException(
                    status_code=400,
                    detail="masked echo cannot be persisted as a real api_keys entry",
                )
    if body.api_key is not None:
        cfg.llm.api_key = body.api_key
    if body.api_keys is not None:
        cfg.llm.api_keys = body.api_keys
    if body.append_api_keys:
        cfg.llm.api_keys = list(cfg.llm.api_keys) + [
            k for k in body.append_api_keys if k not in cfg.llm.api_keys
        ]
    if body.base_url is not None:
        validate_base_url(body.base_url)
        cfg.llm.base_url = body.base_url
    if body.model is not None:
        cfg.llm.model = body.model
    if body.temperature is not None:
        cfg.llm.temperature = body.temperature
    if body.max_tokens is not None:
        cfg.llm.max_tokens = int(body.max_tokens)
    if body.cheap_model is not None:
        cfg.llm.cheap_model = body.cheap_model
    if body.cheap_base_url is not None:
        validate_base_url(body.cheap_base_url)
        cfg.llm.cheap_base_url = body.cheap_base_url
    if body.layer1_model is not None:
        cfg.llm.layer1_model = body.layer1_model
    if body.layer2_model is not None:
        cfg.llm.layer2_model = body.layer2_model
    if body.language is not None:
        cfg.pipeline.language = body.language
        I18n().set_language(body.language)
    if body.enable_self_review is not None:
        cfg.pipeline.enable_self_review = body.enable_self_review
    if body.self_review_threshold is not None:
        cfg.pipeline.self_review_threshold = body.self_review_threshold
    if body.image_provider is not None:
        cfg.pipeline.image_provider = body.image_provider
    if body.codex_model is not None:
        cfg.pipeline.codex_model = body.codex_model
    if body.hf_token is not None:
        cfg.pipeline.hf_token = body.hf_token
    if body.hf_image_model is not None:
        cfg.pipeline.hf_image_model = body.hf_image_model
    if body.image_prompt_style is not None:
        cfg.pipeline.image_prompt_style = body.image_prompt_style
    # Feature toggles (plain on/off, no gate)
    for _attr in (
        "enable_drama_climax",
        "enable_pipeline_overlay",
        "enable_chapter_illustration",
        "enable_simulation_transcript",
    ):
        _val = getattr(body, _attr, None)
        if _val is not None:
            setattr(cfg.pipeline, _attr, _val)
    # FlowKit persistence (gate already enforced above)
    for _attr in (
        "flowkit_enabled",
        "flowkit_port",
        "flowkit_style_reference_path",
        "flowkit_concurrent_workers_max",
        "flowkit_workers_ramp_threshold",
        "flowkit_veo_poll_interval",
        "flowkit_account_warning_shown",
        "flowkit_risk_acknowledged",
        "flowkit_image_input_type_split",
        "flowkit_callback_hmac_required",
        "flowkit_use_refiner",
        "flowkit_request_timeout",
        "flowkit_aspect_ratio",
        "flowkit_project_id",
    ):
        _val = getattr(body, _attr, None)
        if _val is not None:
            setattr(cfg.pipeline, _attr, _val)
    try:
        cfg.save()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # Reset LLM client singleton
    from services.llm_client import LLMClient

    LLMClient.reset()
    return {"status": "ok"}


@router.post("/test-connection", dependencies=[_CONFIGURE_PIPELINE])
def test_connection():
    """Test LLM connection with current settings + all additional profiles."""
    from services.llm_client import LLMClient

    LLMClient.reset()
    client = LLMClient()
    cfg = ConfigManager()

    # Test primary
    ok, msg = client.check_connection()
    results = [{"name": "Primary", "ok": ok, "message": msg}]

    # Test each profile (fallback_models) — 30s aggregate timeout guard.
    # Per-profile results are persisted onto the fallback_models dict so the
    # UI can surface the last status on page reload (it was previously kept
    # only in React state and lost on refresh).
    profiles = list(cfg.llm.fallback_models)
    now_iso = datetime.now(timezone.utc).isoformat()
    _fanout_deadline = time.monotonic() + 30
    for i, fb in enumerate(profiles):
        name = fb.get("name", f"Profile-{i + 1}")
        if fb.get("enabled") is False:
            results.append({"name": name, "ok": None, "message": "disabled"})
            continue
        if time.monotonic() >= _fanout_deadline:
            results.append(
                {
                    "name": name,
                    "ok": None,
                    "message": "skipped — aggregate timeout (30s) exceeded",
                }
            )
            continue
        base_url = fb.get("base_url", "")
        api_key = fb.get("api_key", "")
        model = fb.get("model", "")
        if not base_url or not api_key or not model:
            fb_ok, fb_msg = False, "missing config"
        else:
            fb_ok, fb_msg = client.check_provider(base_url, api_key, model)
        results.append({"name": name, "ok": fb_ok, "message": fb_msg})
        fb["last_test_ok"] = fb_ok
        fb["last_tested_at"] = now_iso
        fb["last_test_message"] = fb_msg

    cfg.llm.fallback_models = profiles
    try:
        cfg.save()
    except Exception as e:  # pragma: no cover — persistence is best-effort here
        logger.warning("test-connection persist failed: %s", e)

    all_ok = all(r["ok"] for r in results if r["ok"] is not None)
    return {
        "ok": all_ok,
        "message": msg if not all_ok else "All providers OK",
        "profiles": results,
    }


@router.get("/languages")
def get_languages():
    """Return supported languages."""
    return {"languages": SUPPORTED_LANGUAGES, "current": I18n().lang}


@router.get("/presets")
def get_presets():
    """Return pipeline presets."""
    return {"presets": PIPELINE_PRESETS}


@router.post("/presets/{key}", dependencies=[_CONFIGURE_PIPELINE])
def apply_preset(key: str):
    """Apply a pipeline preset by key."""
    preset = PIPELINE_PRESETS.get(key)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{key}' not found")
    cfg = ConfigManager()
    for field_name, value in preset.items():
        if field_name == "label":
            continue
        if hasattr(cfg.pipeline, field_name):
            setattr(cfg.pipeline, field_name, value)
    cfg.save()
    return {"status": "ok", "label": preset.get("label", key)}


@router.get("/provider-presets")
def get_provider_presets():
    """Return the "Quick provider" setup cards for the Settings UI.

    Single source of truth — the frontend renders these instead of a hardcoded
    list, so adding a provider here makes it appear in the UI with no frontend
    change. See config/presets.py::PROVIDER_PRESETS.
    """
    return {"presets": PROVIDER_PRESETS}


@router.post("/profiles/detect", dependencies=[_MANAGE_API_KEYS])
def detect_provider(body: ProfileCreate):
    """Detect provider from API key prefix — returns provider info without saving."""
    detected = _detect_provider_from_key(body.api_key) if body.api_key else None
    if not detected:
        return {"detected": False}
    return {
        "detected": True,
        "provider": _detect_provider_name(detected["base_url"]),
        "name": detected["name"],
        "base_url": detected["base_url"],
        "model": detected["model"],
    }


class ModelsRequest(BaseModel):
    """Request body for fetching models from a provider."""

    base_url: str = ""
    api_key: str = ""


@router.post("/provider/models", dependencies=[_MANAGE_API_KEYS])
def get_provider_models(body: ModelsRequest):
    """Fetch available models from a provider (OpenRouter, Kyma, etc.)."""
    validate_base_url(body.base_url)
    provider = _detect_provider_name(body.base_url)
    models = []

    if provider == "openrouter":
        try:
            from services.openrouter_model_discovery import get_free_models

            models = [
                {"id": m, "label": m.split("/")[-1].replace(":free", "")}
                for m in get_free_models(body.api_key)
            ]
        except Exception as e:
            return {"provider": provider, "models": [], "error": str(e)}

    elif provider == "kyma":
        try:
            from services.kyma_model_discovery import get_kyma_models

            models = [{"id": m, "label": m} for m in get_kyma_models(body.api_key)]
        except Exception as e:
            return {"provider": provider, "models": [], "error": str(e)}

    elif provider == "anthropic":
        models = [
            {"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4"},
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5"},
            {"id": "claude-opus-4-20250514", "label": "Claude Opus 4"},
        ]

    elif provider == "openai":
        models = [
            {"id": "gpt-4o", "label": "GPT-4o"},
            {"id": "gpt-4o-mini", "label": "GPT-4o Mini"},
            {"id": "gpt-4-turbo", "label": "GPT-4 Turbo"},
        ]

    elif provider == "gemini":
        models = [
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash"},
            {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro"},
            {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
        ]

    return {"provider": provider, "models": models}


@router.post("/profiles", dependencies=[_MANAGE_API_KEYS])
def add_profile(body: ProfileCreate):
    """Add an API provider profile. Auto-detects provider from key prefix if fields empty."""
    if _is_masked_echo(body.api_key):
        raise HTTPException(
            status_code=400,
            detail="masked echo cannot be persisted as a real api_key",
        )
    detected = _detect_provider_from_key(body.api_key) if body.api_key else None
    cfg = ConfigManager()
    profile = {
        "name": body.name or (detected or {}).get("name", "Custom"),
        "base_url": body.base_url or (detected or {}).get("base_url", ""),
        "api_key": body.api_key,
        "model": body.model or (detected or {}).get("model", ""),
        "enabled": body.enabled,
    }
    if not profile["base_url"]:
        raise HTTPException(
            status_code=400,
            detail="Could not detect provider. Provide base_url manually.",
        )
    validate_base_url(profile["base_url"])
    # If no primary key set, use this provider as primary too
    if not cfg.llm.api_key:
        cfg.llm.api_key = profile["api_key"]
        cfg.llm.base_url = profile["base_url"]
        cfg.llm.model = profile["model"]
    cfg.llm.fallback_models = list(cfg.llm.fallback_models) + [profile]
    try:
        cfg.save()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from services.llm_client import LLMClient

    LLMClient.reset()
    return {
        "status": "ok",
        "index": len(cfg.llm.fallback_models) - 1,
        "detected": _detect_provider_name(profile["base_url"]),
        "name": profile["name"],
    }


@router.put("/profiles/{index}", dependencies=[_MANAGE_API_KEYS])
def update_profile(index: int, body: ProfileCreate):
    """Update an API provider profile."""
    if _is_masked_echo(body.api_key):
        raise HTTPException(
            status_code=400,
            detail="masked echo cannot be persisted as a real api_key",
        )
    cfg = ConfigManager()
    profiles = list(cfg.llm.fallback_models)
    if index < 0 or index >= len(profiles):
        raise HTTPException(status_code=404, detail="Profile index out of range")
    existing_key = profiles[index].get("api_key", "")
    validate_base_url(body.base_url)
    profiles[index] = {
        "name": body.name,
        "base_url": body.base_url,
        "api_key": body.api_key if body.api_key else existing_key,
        "model": body.model,
        "enabled": body.enabled,
    }
    cfg.llm.fallback_models = profiles
    try:
        cfg.save()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from services.llm_client import LLMClient

    LLMClient.reset()
    return {"status": "ok"}


@router.delete("/profiles/{index}", dependencies=[_MANAGE_API_KEYS])
def delete_profile(index: int):
    """Remove an API provider profile."""
    cfg = ConfigManager()
    profiles = list(cfg.llm.fallback_models)
    if index < 0 or index >= len(profiles):
        raise HTTPException(status_code=404, detail="Profile index out of range")
    profiles.pop(index)
    cfg.llm.fallback_models = profiles
    try:
        cfg.save()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    from services.llm_client import LLMClient

    LLMClient.reset()
    return {"status": "ok", "remaining": len(profiles)}


@router.patch("/profiles/{index}/toggle", dependencies=[_MANAGE_API_KEYS])
def toggle_profile(index: int):
    """Toggle enabled state of a profile."""
    cfg = ConfigManager()
    profiles = list(cfg.llm.fallback_models)
    if index < 0 or index >= len(profiles):
        raise HTTPException(status_code=404, detail="Profile index out of range")
    profiles[index]["enabled"] = not profiles[index].get("enabled", True)
    cfg.llm.fallback_models = profiles
    cfg.save()
    from services.llm_client import LLMClient

    LLMClient.reset()
    return {"status": "ok", "enabled": profiles[index]["enabled"]}


@router.get("/cache-stats", dependencies=[_CONFIGURE_PIPELINE])
def cache_stats():
    """Return LLM cache statistics."""
    from services.llm_cache import LLMCache

    return LLMCache(ttl_days=ConfigManager().llm.cache_ttl_days).stats()


@router.delete("/api-keys/{index}", dependencies=[_MANAGE_API_KEYS])
def remove_api_key(index: int):
    """Remove an additional API key by index."""
    cfg = ConfigManager()
    keys = list(cfg.llm.api_keys)
    if index < 0 or index >= len(keys):
        raise HTTPException(status_code=404, detail="Key index out of range")
    keys.pop(index)
    cfg.llm.api_keys = keys
    cfg.save()
    from services.llm_client import LLMClient

    LLMClient.reset()
    return {"status": "ok", "remaining": len(keys)}


@router.delete("/cache", dependencies=[_CONFIGURE_PIPELINE])
def clear_cache():
    """Clear LLM cache."""
    from services.llm_cache import LLMCache

    LLMCache().clear()
    return {"status": "ok"}
