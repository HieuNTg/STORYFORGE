"""OpenRouter dynamic model discovery with 24-hour JSON file cache."""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_CACHE_FILE = "data/openrouter_models_cache.json"
_CACHE_TTL_SECONDS = 86400  # 24 hours

# Hardcoded fallback presets — used when API is unreachable
_FALLBACK_FREE_MODELS = [
    "qwen/qwen3.6-plus-preview:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nvidia/nemotron-3-nano-30b-a3b:free",
    "stepfun/step-3.5-flash:free",
    "minimax/minimax-m2.5:free",
]

# Minimum context window required for story generation
_MIN_CONTEXT_TOKENS = 8192


def _load_cache() -> Optional[dict]:
    """Load cached model list. Returns None if missing or expired."""
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("cached_at", 0) > _CACHE_TTL_SECONDS:
            return None
        return data
    except Exception as e:
        logger.debug(f"Cache load failed: {e}")
        return None


def _save_cache(models: list[dict]) -> None:
    """Persist model list to cache file."""
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"cached_at": time.time(), "models": models}, f, indent=2)
    except Exception as e:
        logger.warning(f"Cache save failed: {e}")


def _fetch_from_api(api_key: str = "") -> Optional[list[dict]]:
    """Fetch model list from OpenRouter API. Returns raw model dicts or None."""
    try:
        import urllib.request

        req = urllib.request.Request(_OPENROUTER_MODELS_URL)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("HTTP-Referer", "https://storyforge.app")

        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            return raw.get("data", [])
    except Exception as e:
        logger.warning(f"OpenRouter API unreachable: {e}")
        return None


def _is_free(model: dict) -> bool:
    """Return True if all pricing fields are zero (free tier)."""
    pricing = model.get("pricing", {})
    try:
        prompt_cost = float(pricing.get("prompt", "1") or "1")
        completion_cost = float(pricing.get("completion", "1") or "1")
        return prompt_cost == 0.0 and completion_cost == 0.0
    except (ValueError, TypeError):
        return False


def _meets_requirements(model: dict) -> bool:
    """Return True if model has sufficient context window for story gen."""
    ctx = model.get("context_length", 0) or 0
    return int(ctx) >= _MIN_CONTEXT_TOKENS


def get_free_models(api_key: str = "", force_refresh: bool = False) -> list[str]:
    """Return list of free model IDs available on OpenRouter.

    Priority order:
    1. Live API with 24h cache
    2. Expired cache (stale-but-valid fallback)
    3. Hardcoded fallback list
    """
    # Try cache first (unless forced refresh)
    if not force_refresh:
        cached = _load_cache()
        if cached:
            ids = [m["id"] for m in cached["models"]]
            logger.debug(f"Model discovery: {len(ids)} models from cache")
            return ids

    # Try live API
    raw_models = _fetch_from_api(api_key)

    if raw_models is not None:
        filtered = [
            m for m in raw_models
            if _is_free(m) and _meets_requirements(m) and m.get("id")
        ]
        _save_cache(filtered)
        ids = [m["id"] for m in filtered]
        logger.info(f"Model discovery: {len(ids)} free models fetched from OpenRouter")
        return ids

    # API failed — try stale cache
    stale_path = _CACHE_FILE
    if os.path.exists(stale_path):
        try:
            with open(stale_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ids = [m["id"] for m in data.get("models", [])]
            if ids:
                logger.warning(f"Model discovery: using stale cache ({len(ids)} models)")
                return ids
        except Exception:
            pass

    # Final fallback
    logger.warning("Model discovery: using hardcoded fallback model list")
    return list(_FALLBACK_FREE_MODELS)


def get_model_info(model_id: str, api_key: str = "") -> Optional[dict]:
    """Return metadata for a specific model ID, or None if not found."""
    cached = _load_cache()
    if cached:
        for m in cached["models"]:
            if m.get("id") == model_id:
                return m

    # Refresh and retry
    raw = _fetch_from_api(api_key)
    if raw:
        for m in raw:
            if m.get("id") == model_id:
                return m
    return None


def validate_model_id(model_id: str, api_key: str = "") -> bool:
    """Return True if model_id exists among current free OpenRouter models."""
    return model_id in get_free_models(api_key)


def refresh_cache(api_key: str = "") -> list[str]:
    """Force refresh the model cache and return updated model ID list."""
    return get_free_models(api_key=api_key, force_refresh=True)
