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
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import ConfigManager, PIPELINE_PRESETS, MODEL_PRESETS
from services.i18n import I18n, SUPPORTED_LANGUAGES

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
    if "localhost" in url or "127.0.0.1" in url:
        return "local"
    return "custom"


PROVIDER_FROM_KEY = [
    ("sk-ant-", {"name": "Anthropic", "base_url": "https://api.anthropic.com/v1/", "model": "claude-haiku-4-5-20251001"}),
    ("sk-or-",  {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "model": "qwen/qwen3.6-plus:free"}),
    ("sk-proj-", {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"}),
    ("sk-",     {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"}),
    ("AIza",    {"name": "Google Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-flash"}),
]


def _detect_provider_from_key(api_key: str) -> dict | None:
    """Auto-detect provider config from API key prefix."""
    for prefix, config in PROVIDER_FROM_KEY:
        if api_key.startswith(prefix):
            return config
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
    hf_token: Optional[str] = None
    hf_image_model: Optional[str] = None
    image_prompt_style: Optional[str] = None


@router.get("")
def get_config():
    """Return current config (API key and HF token masked)."""
    cfg = ConfigManager()
    key = cfg.llm.api_key or ""
    masked_key = key[:4] + "***" + key[-4:] if len(key) > 8 else "***"
    hf_tok = cfg.pipeline.hf_token or ""
    masked_hf_token = "***" + hf_tok[-4:] if len(hf_tok) > 4 else ("***" if hf_tok else "")
    profiles_masked = []
    for fb in cfg.llm.fallback_models:
        profiles_masked.append({
            "name": fb.get("name", fb.get("model", "Unknown")),
            "provider": _detect_provider_name(fb.get("base_url", "")),
            "base_url": fb.get("base_url", ""),
            "api_key_masked": _mask_key(fb.get("api_key", "")),
            "model": fb.get("model", ""),
            "enabled": fb.get("enabled", True),
        })
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
                for k in [raw if isinstance(raw, str) else (raw.get("key") or raw.get("api_key") or "")]
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
            "hf_token_masked": masked_hf_token,
            "hf_image_model": cfg.pipeline.hf_image_model,
            "image_prompt_style": cfg.pipeline.image_prompt_style,
        },
    }


@router.put("")
def save_config(body: ConfigUpdate):
    """Save settings to config.json."""
    cfg = ConfigManager()
    if body.api_key is not None:
        cfg.llm.api_key = body.api_key
    if body.api_keys is not None:
        cfg.llm.api_keys = body.api_keys
    if body.append_api_keys:
        cfg.llm.api_keys = list(cfg.llm.api_keys) + [k for k in body.append_api_keys if k not in cfg.llm.api_keys]
    if body.base_url is not None:
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
    if body.hf_token is not None:
        cfg.pipeline.hf_token = body.hf_token
    if body.hf_image_model is not None:
        cfg.pipeline.hf_image_model = body.hf_image_model
    if body.image_prompt_style is not None:
        cfg.pipeline.image_prompt_style = body.image_prompt_style
    cfg.save()
    # Reset LLM client singleton
    from services.llm_client import LLMClient
    LLMClient.reset()
    return {"status": "ok"}


@router.post("/test-connection")
def test_connection():
    """Test LLM connection with current settings."""
    from services.llm_client import LLMClient
    LLMClient.reset()
    ok, msg = LLMClient().check_connection()
    return {"ok": ok, "message": msg}


@router.get("/languages")
def get_languages():
    """Return supported languages."""
    return {"languages": SUPPORTED_LANGUAGES, "current": I18n().lang}


@router.get("/presets")
def get_presets():
    """Return pipeline presets."""
    return {"presets": PIPELINE_PRESETS}


@router.post("/presets/{key}")
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


@router.get("/model-presets")
def get_model_presets():
    """Return available model presets (OpenRouter free tiers, etc.)."""
    return {"presets": {k: {"label": v["label"]} for k, v in MODEL_PRESETS.items()}}


@router.post("/model-presets/{key}")
def apply_model_preset(key: str):
    """Apply a model preset — sets LLM config fields (base_url, model, fallbacks, etc.)."""
    preset = MODEL_PRESETS.get(key)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Model preset '{key}' not found")
    cfg = ConfigManager()
    for field_name, value in preset.items():
        if field_name == "label":
            continue
        if hasattr(cfg.llm, field_name):
            setattr(cfg.llm, field_name, value)
    cfg.save()
    # Reset LLM client to pick up new config
    from services.llm_client import LLMClient
    LLMClient.reset()
    return {"status": "ok", "label": preset.get("label", key)}


@router.post("/profiles/detect")
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


@router.post("/profiles")
def add_profile(body: ProfileCreate):
    """Add an API provider profile. Auto-detects provider from key prefix if fields empty."""
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
        raise HTTPException(status_code=400, detail="Could not detect provider. Provide base_url manually.")
    cfg.llm.fallback_models = list(cfg.llm.fallback_models) + [profile]
    cfg.save()
    from services.llm_client import LLMClient
    LLMClient.reset()
    return {
        "status": "ok",
        "index": len(cfg.llm.fallback_models) - 1,
        "detected": _detect_provider_name(profile["base_url"]),
        "name": profile["name"],
    }


@router.put("/profiles/{index}")
def update_profile(index: int, body: ProfileCreate):
    """Update an API provider profile."""
    cfg = ConfigManager()
    profiles = list(cfg.llm.fallback_models)
    if index < 0 or index >= len(profiles):
        raise HTTPException(status_code=404, detail="Profile index out of range")
    existing_key = profiles[index].get("api_key", "")
    profiles[index] = {
        "name": body.name,
        "base_url": body.base_url,
        "api_key": body.api_key if body.api_key else existing_key,
        "model": body.model,
        "enabled": body.enabled,
    }
    cfg.llm.fallback_models = profiles
    cfg.save()
    from services.llm_client import LLMClient
    LLMClient.reset()
    return {"status": "ok"}


@router.delete("/profiles/{index}")
def delete_profile(index: int):
    """Remove an API provider profile."""
    cfg = ConfigManager()
    profiles = list(cfg.llm.fallback_models)
    if index < 0 or index >= len(profiles):
        raise HTTPException(status_code=404, detail="Profile index out of range")
    profiles.pop(index)
    cfg.llm.fallback_models = profiles
    cfg.save()
    from services.llm_client import LLMClient
    LLMClient.reset()
    return {"status": "ok", "remaining": len(profiles)}


@router.patch("/profiles/{index}/toggle")
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


@router.get("/cache-stats")
def cache_stats():
    """Return LLM cache statistics."""
    from services.llm_cache import LLMCache
    return LLMCache(ttl_days=ConfigManager().llm.cache_ttl_days).stats()


@router.delete("/api-keys/{index}")
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


@router.delete("/cache")
def clear_cache():
    """Clear LLM cache."""
    from services.llm_cache import LLMCache
    LLMCache().clear()
    return {"status": "ok"}
