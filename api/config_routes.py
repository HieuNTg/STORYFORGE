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

import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import ConfigManager, PIPELINE_PRESETS, MODEL_PRESETS
from services.i18n import I18n, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/config", tags=["config"])


class ConfigUpdate(BaseModel):
    """Request body for saving settings."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    cheap_model: Optional[str] = None
    cheap_base_url: Optional[str] = None
    backend_type: Optional[str] = None
    language: Optional[str] = None
    layer1_model: Optional[str] = None
    layer2_model: Optional[str] = None
    layer3_model: Optional[str] = None
    enable_self_review: Optional[bool] = None
    self_review_threshold: Optional[float] = None


@router.get("")
def get_config():
    """Return current config (API key masked)."""
    cfg = ConfigManager()
    key = cfg.llm.api_key or ""
    masked_key = key[:4] + "***" + key[-4:] if len(key) > 8 else "***"
    return {
        "llm": {
            "api_key_masked": masked_key,
            "base_url": cfg.llm.base_url,
            "model": cfg.llm.model,
            "temperature": cfg.llm.temperature,
            "max_tokens": cfg.llm.max_tokens,
            "cheap_model": cfg.llm.cheap_model,
            "cheap_base_url": cfg.llm.cheap_base_url,
            "backend_type": cfg.llm.backend_type,
            "layer1_model": cfg.llm.layer1_model,
            "layer2_model": cfg.llm.layer2_model,
            "layer3_model": cfg.llm.layer3_model,
        },
        "pipeline": {
            "language": cfg.pipeline.language,
            "enable_self_review": cfg.pipeline.enable_self_review,
            "self_review_threshold": cfg.pipeline.self_review_threshold,
        },
    }


@router.put("")
def save_config(body: ConfigUpdate):
    """Save settings to config.json."""
    cfg = ConfigManager()
    if body.api_key is not None:
        cfg.llm.api_key = body.api_key
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
    if body.backend_type is not None:
        cfg.llm.backend_type = body.backend_type
    if body.layer1_model is not None:
        cfg.llm.layer1_model = body.layer1_model
    if body.layer2_model is not None:
        cfg.llm.layer2_model = body.layer2_model
    if body.layer3_model is not None:
        cfg.llm.layer3_model = body.layer3_model
    if body.language is not None:
        cfg.pipeline.language = body.language
        I18n().set_language(body.language)
    if body.enable_self_review is not None:
        cfg.pipeline.enable_self_review = body.enable_self_review
    if body.self_review_threshold is not None:
        cfg.pipeline.self_review_threshold = body.self_review_threshold
    cfg.save()
    # Reset LLM client singleton
    from services.llm_client import LLMClient
    LLMClient.reset()
    return {"status": "ok"}


@router.post("/test-connection")
def test_connection():
    """Test LLM connection with current settings."""
    try:
        from services.llm_client import LLMClient
        LLMClient.reset()
        ok, msg = LLMClient().check_connection()
        return {"ok": ok, "message": msg}
    except Exception as e:
        return {"ok": False, "message": str(e)}


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


@router.get("/cache-stats")
def cache_stats():
    """Return LLM cache statistics."""
    try:
        from services.llm_cache import LLMCache
        s = LLMCache(ttl_days=ConfigManager().llm.cache_ttl_days).stats()
        return s
    except Exception as e:
        return {"error": str(e)}


@router.delete("/cache")
def clear_cache():
    """Clear LLM cache."""
    try:
        from services.llm_cache import LLMCache
        LLMCache().clear()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
