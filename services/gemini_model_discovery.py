"""Gemini model discovery — lists available models via google-genai SDK with 24h cache.

Unlike OpenRouter (public REST endpoint), Gemini requires a keyed SDK call. We cache
the result to avoid a discovery call per request. If discovery fails (no SDK, no
network, bad key) we fall back to a hardcoded list of known-stable free-tier models
so the fallback chain still works when the primary model hits 429.
"""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_FILE = "data/gemini_models_cache.json"
_CACHE_TTL_SECONDS = 86400  # 24 hours

# Stable free-tier text models, newest-capable first. Each has a SEPARATE daily
# quota bucket — when one hits 429 RESOURCE_EXHAUSTED we try the next.
# Includes Gemma (open-weights, same API, separate quotas) as secondary fallback.
_FALLBACK_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash",
    "gemma-4-31b-it",
    "gemma-4-26b-a4b-it",
    "gemma-3-27b-it",
    "gemma-3-12b-it",
]


def _load_cache(cache_key: str) -> Optional[list[str]]:
    if not os.path.exists(_CACHE_FILE):
        return None
    try:
        with open(_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("key_hash") != cache_key:
            return None
        if time.time() - data.get("cached_at", 0) > _CACHE_TTL_SECONDS:
            return None
        return data.get("models", [])
    except Exception as e:
        logger.debug(f"Gemini cache load failed: {e}")
        return None


def _save_cache(cache_key: str, models: list[str]) -> None:
    os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
    try:
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"cached_at": time.time(), "key_hash": cache_key, "models": models},
                f, indent=2,
            )
    except Exception as e:
        logger.warning(f"Gemini cache save failed: {e}")


_EXCLUDE_KEYWORDS = (
    "embedding", "aqa",
    "image", "tts", "audio", "vision-only",
    "robotics", "computer-use", "lyria", "nano-banana",
    "deep-research", "customtools",
)


def _fetch_from_api(api_key: str) -> Optional[list[str]]:
    """List generateContent-capable text models from Gemini API.

    Filters out image/TTS/audio/robotics/embedding variants — we only want
    general text-generation models for the fallback chain.
    """
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        models: list[str] = []
        for m in client.models.list():
            name = getattr(m, "name", "") or ""
            if name.startswith("models/"):
                name = name[len("models/"):]
            if not name:
                continue
            # Only include generateContent-capable models (if SDK exposes it)
            supported = (
                getattr(m, "supported_actions", None)
                or getattr(m, "supported_generation_methods", None)
                or []
            )
            if supported and "generateContent" not in supported:
                continue
            # Skip non-text variants (image/TTS/robotics/etc.)
            lname = name.lower()
            if any(kw in lname for kw in _EXCLUDE_KEYWORDS):
                continue
            # Keep gemini-* and gemma-* (both text-gen on the same API,
            # with SEPARATE daily-quota buckets from Gemini models).
            if not (lname.startswith("gemini-") or lname.startswith("gemma-")):
                continue
            models.append(name)
        return models or None
    except Exception as e:
        logger.warning(f"Gemini API unreachable: {e}")
        return None


def _key_hash(api_key: str) -> str:
    """Short deterministic hash so we don't bust cache across sessions but
    still invalidate when the user swaps keys."""
    import hashlib
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16] if api_key else "nokey"


def get_gemini_models(api_key: str = "") -> list[str]:
    """Return ordered list of usable Gemini model IDs (newest first).

    Priority:
      1. 24h disk cache (per-key)
      2. Live API discovery
      3. Hardcoded fallback list
    """
    cache_key = _key_hash(api_key)

    cached = _load_cache(cache_key)
    if cached:
        return cached

    if api_key:
        fresh = _fetch_from_api(api_key)
        if fresh:
            ordered = _order_models(fresh)
            _save_cache(cache_key, ordered)
            return ordered

    return list(_FALLBACK_MODELS)


def _order_models(models: list[str]) -> list[str]:
    """Ordering for fallback chain:
      1. Stable over preview/exp (primary reliability concern).
      2. Newer version first (within stability tier).
      3. flash-lite > flash > pro (cheap tier = more free quota, fewer 429s).
      4. Strip '-latest' and '-NNN' revision suffixes to prefer canonical ID.
    Primary model is prepended separately by caller, so ordering here only
    controls which alternate to try AFTER primary is exhausted.
    """
    import re

    def sort_key(m: str) -> tuple:
        # Family: gemini first, gemma after (separate quota, but Gemma is
        # instruction-tuned open-weights — safer as secondary fallback).
        family = 0 if m.startswith("gemini-") else 1
        is_preview = 1 if ("preview" in m or "exp" in m) else 0
        ver_match = re.search(r"(?:gemini|gemma)-?(\d+(?:\.\d+)?)", m)
        version = float(ver_match.group(1)) if ver_match else 0.0
        if "flash-lite" in m:
            tier = 0  # cheapest → tried first as fallback
        elif "flash" in m:
            tier = 1
        else:
            tier = 2  # pro / gemma base: highest cost, last resort
        # Prefer canonical IDs over '-latest' or '-NNN' revisions
        rev_penalty = 1 if ("-latest" in m or re.search(r"-\d{3}$", m)) else 0
        return (family, is_preview, -version, tier, rev_penalty, m)

    seen = set()
    out = []
    for m in sorted(models, key=sort_key):
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out
