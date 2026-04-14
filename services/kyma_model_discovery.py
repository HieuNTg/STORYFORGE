"""Kyma API dynamic model discovery with 24-hour JSON file cache."""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_KYMA_MODELS_URL = "https://kymaapi.com/v1/models"
_CACHE_FILE = "data/kyma_models_cache.json"
_CACHE_TTL_SECONDS = 86400  # 24 hours

# Hardcoded fallback — used when API unreachable
_FALLBACK_MODELS = [
    "qwen-3.6-plus",
    "deepseek-v3",
    "deepseek-r1",
    "llama-3.3-70b",
    "qwen-3-32b",
    "gemini-2.5-flash",
    "minimax-m2.5",
    "gpt-oss-120b",
]

_MIN_CONTEXT_TOKENS = 8192

_EXCLUDED_PATTERNS = [
    "coder",  # code-only, poor prose
]


def _load_cache() -> Optional[dict]:
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if time.time() - data.get("cached_at", 0) > _CACHE_TTL_SECONDS:
            return None
        return data
    except Exception as e:
        logger.debug(f"Kyma cache load failed: {e}")
        return None


def _save_cache(models: list[dict]) -> None:
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"cached_at": time.time(), "models": models}, f, indent=2)
    except Exception as e:
        logger.warning(f"Kyma cache save failed: {e}")


def _fetch_from_api(api_key: str = "") -> Optional[list[dict]]:
    """Fetch model list from Kyma API."""
    try:
        import urllib.request

        req = urllib.request.Request(_KYMA_MODELS_URL)
        if api_key:
            req.add_header("Authorization", f"Bearer {api_key}")

        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            return raw.get("data", [])
    except Exception as e:
        logger.warning(f"Kyma API unreachable: {e}")
        return None


def _meets_requirements(model: dict) -> bool:
    # Kyma uses 'context_window', OpenRouter uses 'context_length'
    ctx = model.get("context_window") or model.get("context_length") or 0
    if int(ctx) < _MIN_CONTEXT_TOKENS:
        return False
    mid = model.get("id", "").lower()
    return not any(pat in mid for pat in _EXCLUDED_PATTERNS)


def get_kyma_models(api_key: str = "", force_refresh: bool = False) -> list[str]:
    """Return list of available Kyma model IDs.

    Priority: live API (24h cache) -> stale cache -> hardcoded fallback.
    """
    if not force_refresh:
        cached = _load_cache()
        if cached:
            ids = [m["id"] for m in cached["models"]]
            logger.debug(f"Kyma discovery: {len(ids)} models from cache")
            return ids

    raw_models = _fetch_from_api(api_key)

    if raw_models is not None:
        filtered = [m for m in raw_models if _meets_requirements(m) and m.get("id")]
        _save_cache(filtered)
        ids = [m["id"] for m in filtered]
        logger.info(f"Kyma discovery: {len(ids)} models fetched")
        return ids

    # Stale cache fallback
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            ids = [m["id"] for m in data.get("models", [])]
            if ids:
                logger.warning(f"Kyma discovery: using stale cache ({len(ids)} models)")
                return ids
        except Exception:
            pass

    logger.warning("Kyma discovery: using hardcoded fallback")
    return list(_FALLBACK_MODELS)


def refresh_cache(api_key: str = "") -> list[str]:
    return get_kyma_models(api_key=api_key, force_refresh=True)
