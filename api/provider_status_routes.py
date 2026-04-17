"""Provider status API — rate limits and model availability."""

import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/providers", tags=["providers"])


def _get_api_keys_from_config() -> dict[str, str]:
    """Extract API keys for each provider from config."""
    try:
        from config import ConfigManager
        cfg = ConfigManager()

        keys = {}
        base_url = getattr(cfg.llm, "base_url", "") or ""

        # Detect primary provider
        url_lower = base_url.lower()
        if "openrouter" in url_lower:
            keys["openrouter"] = cfg.llm.api_key
        elif "kymaapi.com" in url_lower:
            keys["kyma"] = cfg.llm.api_key
        elif "anthropic.com" in url_lower:
            keys["anthropic"] = cfg.llm.api_key
        elif "googleapis.com" in url_lower or "generativelanguage" in url_lower:
            keys["google"] = cfg.llm.api_key
        elif "z.ai" in url_lower:
            keys["zai"] = cfg.llm.api_key
        else:
            keys["openai"] = cfg.llm.api_key

        # Check for additional keys in fallback_models
        for fb in getattr(cfg.llm, "fallback_models", []) or []:
            if not isinstance(fb, dict):
                continue
            fb_url = fb.get("base_url", "").lower()
            fb_key = fb.get("api_key", "")
            if not fb_key:
                continue
            if "openrouter" in fb_url:
                keys.setdefault("openrouter", fb_key)
            elif "kymaapi.com" in fb_url:
                keys.setdefault("kyma", fb_key)
            elif "anthropic.com" in fb_url:
                keys.setdefault("anthropic", fb_key)
            elif "googleapis.com" in fb_url:
                keys.setdefault("google", fb_key)
            elif "z.ai" in fb_url:
                keys.setdefault("zai", fb_key)

        # Check environment for additional keys
        import os
        if "ANTHROPIC_API_KEY" in os.environ and "anthropic" not in keys:
            keys["anthropic"] = os.environ["ANTHROPIC_API_KEY"]
        if "GOOGLE_AI_API_KEY" in os.environ and "google" not in keys:
            keys["google"] = os.environ["GOOGLE_AI_API_KEY"]
        if "ZAI_API_KEY" in os.environ and "zai" not in keys:
            keys["zai"] = os.environ["ZAI_API_KEY"]

        return keys
    except Exception as e:
        logger.warning(f"Failed to get API keys from config: {e}")
        return {}


@router.get("/status", summary="Get all provider statuses")
async def get_all_provider_status():
    """Get rate limit and model availability for all configured providers."""
    from services.llm.provider_status import get_provider_status_manager

    mgr = get_provider_status_manager()
    api_keys = _get_api_keys_from_config()

    return JSONResponse(content={
        "providers": mgr.get_all_statuses(api_keys),
        "configured_providers": list(api_keys.keys()),
    })


@router.get("/status/{provider_type}", summary="Get specific provider status")
async def get_provider_status(provider_type: str):
    """Get rate limit and model availability for a specific provider."""
    from services.llm.provider_status import get_provider_status_manager

    mgr = get_provider_status_manager()
    api_keys = _get_api_keys_from_config()
    api_key = api_keys.get(provider_type, "")

    return JSONResponse(content=mgr.get_provider_status(provider_type, api_key))


@router.get("/models/{provider_type}", summary="Get available models for provider")
async def get_provider_models(
    provider_type: str,
    refresh: bool = Query(False, description="Force refresh from API"),
):
    """Get list of available models for a provider."""
    from services.llm.provider_status import get_provider_status_manager

    mgr = get_provider_status_manager()
    api_keys = _get_api_keys_from_config()
    api_key = api_keys.get(provider_type, "")

    models = mgr.get_available_models(provider_type, api_key, force_refresh=refresh)

    return JSONResponse(content={
        "provider": provider_type,
        "models": models,
        "count": len(models),
    })


@router.post("/refresh", summary="Force refresh all provider data")
async def refresh_all_providers():
    """Force refresh model lists and clear stale rate limit data."""
    from services.llm.provider_status import get_provider_status_manager

    mgr = get_provider_status_manager()
    api_keys = _get_api_keys_from_config()

    result = mgr.refresh_all(api_keys)

    return JSONResponse(content={
        "status": "refreshed",
        "providers": result,
    })


@router.get("/quota-check", summary="Check if any provider has low quota")
async def check_quota_status(
    threshold: float = Query(0.1, description="Quota threshold (0.0-1.0)"),
):
    """Check quota status across all providers.

    Returns providers with low quota that may need switching.
    """
    from services.llm.provider_status import get_provider_status_manager

    mgr = get_provider_status_manager()
    api_keys = _get_api_keys_from_config()

    low_quota = []
    ok_providers = []

    for ptype, api_key in api_keys.items():
        if mgr.is_quota_low(ptype, api_key, threshold):
            status = mgr.get_rate_limit(ptype, api_key)
            low_quota.append({
                "provider": ptype,
                "quota_pct": status.min_pct if status else None,
                "reset_at": status.reset_at if status else None,
            })
        else:
            ok_providers.append(ptype)

    return JSONResponse(content={
        "low_quota_providers": low_quota,
        "ok_providers": ok_providers,
        "threshold": threshold,
        "should_switch": len(low_quota) > 0,
    })


@router.get("/fallbacks", summary="Get usable fallback models")
async def get_usable_fallbacks(
    provider_type: Optional[str] = Query(None, description="Filter by provider"),
):
    """Get list of usable fallback models with quota info."""
    from services.llm.provider_status import get_provider_status_manager

    mgr = get_provider_status_manager()
    api_keys = _get_api_keys_from_config()

    result = {}
    providers = [provider_type] if provider_type else list(api_keys.keys())

    for ptype in providers:
        api_key = api_keys.get(ptype, "")
        if not api_key:
            continue
        fallbacks = mgr.get_usable_fallbacks(ptype, api_key)
        result[ptype] = fallbacks

    return JSONResponse(content={"fallbacks": result})
