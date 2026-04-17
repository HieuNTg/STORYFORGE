"""Provider status manager — rate limits + model discovery for all LLM providers."""

import json
import logging
import os
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

_CACHE_DIR = "data/provider_status"
_CACHE_TTL_SECONDS = 86400  # 24h for model lists
_RATE_LIMIT_STALE_SECONDS = 300  # 5min for rate limit data


@dataclass
class RateLimitStatus:
    """Rate limit status for a provider/key combo."""
    remaining_requests: Optional[int] = None
    limit_requests: Optional[int] = None
    remaining_tokens: Optional[int] = None
    limit_tokens: Optional[int] = None
    reset_at: Optional[float] = None  # Unix timestamp
    updated_at: float = 0.0

    @property
    def is_stale(self) -> bool:
        return time.time() - self.updated_at > _RATE_LIMIT_STALE_SECONDS

    @property
    def requests_pct(self) -> Optional[float]:
        if self.remaining_requests is not None and self.limit_requests:
            return self.remaining_requests / self.limit_requests
        return None

    @property
    def tokens_pct(self) -> Optional[float]:
        if self.remaining_tokens is not None and self.limit_tokens:
            return self.remaining_tokens / self.limit_tokens
        return None

    @property
    def min_pct(self) -> Optional[float]:
        """Minimum of requests and tokens percentage (most constrained)."""
        pcts = [p for p in [self.requests_pct, self.tokens_pct] if p is not None]
        return min(pcts) if pcts else None

    def to_dict(self) -> dict:
        return {
            "remaining_requests": self.remaining_requests,
            "limit_requests": self.limit_requests,
            "remaining_tokens": self.remaining_tokens,
            "limit_tokens": self.limit_tokens,
            "reset_at": self.reset_at,
            "updated_at": self.updated_at,
            "requests_pct": self.requests_pct,
            "tokens_pct": self.tokens_pct,
            "min_pct": self.min_pct,
            "is_stale": self.is_stale,
        }


@dataclass
class ProviderInfo:
    """Cached info for a provider."""
    provider_type: str
    models: list[str] = field(default_factory=list)
    models_updated_at: float = 0.0
    rate_limits: dict[str, RateLimitStatus] = field(default_factory=dict)  # api_key -> status


# Header mappings per provider
_HEADER_MAPS = {
    "openai": {
        "remaining_requests": ["x-ratelimit-remaining-requests"],
        "limit_requests": ["x-ratelimit-limit-requests"],
        "remaining_tokens": ["x-ratelimit-remaining-tokens"],
        "limit_tokens": ["x-ratelimit-limit-tokens"],
        "reset": ["x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"],
    },
    "anthropic": {
        "remaining_requests": ["anthropic-ratelimit-requests-remaining"],
        "limit_requests": ["anthropic-ratelimit-requests-limit"],
        "remaining_tokens": ["anthropic-ratelimit-tokens-remaining"],
        "limit_tokens": ["anthropic-ratelimit-tokens-limit"],
        "reset": ["anthropic-ratelimit-requests-reset", "anthropic-ratelimit-tokens-reset"],
    },
    "openrouter": {
        "remaining_requests": ["x-ratelimit-remaining"],
        "limit_requests": ["x-ratelimit-limit"],
        "reset": ["x-ratelimit-reset"],
    },
    "google": {
        "remaining_requests": ["x-ratelimit-remaining"],
        "limit_requests": ["x-ratelimit-limit"],
    },
    "kyma": {
        "remaining_requests": ["x-ratelimit-remaining"],
        "limit_requests": ["x-ratelimit-limit"],
    },
    "zai": {
        "remaining_requests": ["x-ratelimit-remaining"],
        "limit_requests": ["x-ratelimit-limit"],
    },
}

# Model discovery endpoints
_MODEL_ENDPOINTS = {
    "openai": "https://api.openai.com/v1/models",
    "anthropic": None,  # No discovery API, hardcoded list
    "openrouter": "https://openrouter.ai/api/v1/models",
    "google": "https://generativelanguage.googleapis.com/v1beta/models",
    "kyma": "https://kymaapi.com/v1/models",
    "zai": "https://api.z.ai/api/paas/v4/models",
}

# Hardcoded model lists for providers without discovery API
_HARDCODED_MODELS = {
    "anthropic": [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
        "claude-3-opus-20240229",
    ],
    "zai": [
        "glm-4.7-flash",
        "glm-4.5-flash",
        "glm-4-air",
    ],
}


class ProviderStatusManager:
    """Singleton manager for provider rate limits and model availability."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._providers: dict[str, ProviderInfo] = {}
        self._data_lock = threading.Lock()
        os.makedirs(_CACHE_DIR, exist_ok=True)
        self._load_cached_data()

    def _cache_file(self, provider_type: str) -> str:
        return os.path.join(_CACHE_DIR, f"{provider_type}.json")

    def _load_cached_data(self) -> None:
        """Load cached model lists from disk."""
        for ptype in _MODEL_ENDPOINTS:
            cache_file = self._cache_file(ptype)
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self._providers[ptype] = ProviderInfo(
                        provider_type=ptype,
                        models=data.get("models", []),
                        models_updated_at=data.get("updated_at", 0),
                    )
                except Exception as e:
                    logger.debug(f"Failed to load cache for {ptype}: {e}")

    def _save_models_cache(self, provider_type: str, models: list[str]) -> None:
        """Persist model list to disk."""
        try:
            with open(self._cache_file(provider_type), "w", encoding="utf-8") as f:
                json.dump({"models": models, "updated_at": time.time()}, f)
        except Exception as e:
            logger.warning(f"Failed to save cache for {provider_type}: {e}")

    def _get_or_create_provider(self, provider_type: str) -> ProviderInfo:
        with self._data_lock:
            if provider_type not in self._providers:
                self._providers[provider_type] = ProviderInfo(provider_type=provider_type)
            return self._providers[provider_type]

    # -------------------------------------------------------------------------
    # Rate Limit Tracking
    # -------------------------------------------------------------------------

    def extract_rate_limits(
        self, provider_type: str, api_key: str, headers: dict
    ) -> Optional[RateLimitStatus]:
        """Extract and store rate limit info from response headers."""
        if provider_type not in _HEADER_MAPS:
            return None

        header_map = _HEADER_MAPS[provider_type]
        headers_lower = {k.lower(): v for k, v in headers.items()}

        def get_int(keys: list[str]) -> Optional[int]:
            for k in keys:
                if k.lower() in headers_lower:
                    try:
                        return int(headers_lower[k.lower()])
                    except (ValueError, TypeError):
                        pass
            return None

        def get_reset(keys: list[str]) -> Optional[float]:
            for k in keys:
                if k.lower() in headers_lower:
                    val = headers_lower[k.lower()]
                    try:
                        ts = float(val)
                        # OpenRouter uses ms, others use seconds
                        if ts > 1e12:
                            ts = ts / 1000.0
                        return ts
                    except (ValueError, TypeError):
                        pass
            return None

        status = RateLimitStatus(
            remaining_requests=get_int(header_map.get("remaining_requests", [])),
            limit_requests=get_int(header_map.get("limit_requests", [])),
            remaining_tokens=get_int(header_map.get("remaining_tokens", [])),
            limit_tokens=get_int(header_map.get("limit_tokens", [])),
            reset_at=get_reset(header_map.get("reset", [])),
            updated_at=time.time(),
        )

        # Only store if we got meaningful data
        if status.remaining_requests is not None or status.remaining_tokens is not None:
            prov = self._get_or_create_provider(provider_type)
            key_hash = self._hash_key(api_key)
            with self._data_lock:
                prov.rate_limits[key_hash] = status
            logger.debug(
                f"Rate limit tracked: {provider_type} req={status.remaining_requests}/{status.limit_requests} "
                f"tok={status.remaining_tokens}/{status.limit_tokens}"
            )
            return status
        return None

    def get_rate_limit(self, provider_type: str, api_key: str) -> Optional[RateLimitStatus]:
        """Get cached rate limit status for a provider/key."""
        prov = self._providers.get(provider_type)
        if not prov:
            return None
        key_hash = self._hash_key(api_key)
        return prov.rate_limits.get(key_hash)

    def is_quota_low(
        self, provider_type: str, api_key: str, threshold: float = 0.1
    ) -> bool:
        """Return True if quota is below threshold (preemptive switch trigger)."""
        status = self.get_rate_limit(provider_type, api_key)
        if not status or status.is_stale:
            return False  # No data or stale — don't preempt
        pct = status.min_pct
        if pct is not None and pct < threshold:
            return True
        return False

    @staticmethod
    def _hash_key(api_key: str) -> str:
        """Hash API key for storage (privacy)."""
        if len(api_key) < 12:
            return api_key
        return f"{api_key[:8]}...{api_key[-4:]}"

    # -------------------------------------------------------------------------
    # Model Discovery
    # -------------------------------------------------------------------------

    def get_available_models(
        self, provider_type: str, api_key: str = "", force_refresh: bool = False
    ) -> list[str]:
        """Get list of available models for a provider."""
        prov = self._get_or_create_provider(provider_type)

        # Check cache validity
        cache_valid = (
            prov.models
            and not force_refresh
            and time.time() - prov.models_updated_at < _CACHE_TTL_SECONDS
        )
        if cache_valid:
            return prov.models

        # Try API discovery
        models = self._fetch_models(provider_type, api_key)
        if models:
            with self._data_lock:
                prov.models = models
                prov.models_updated_at = time.time()
            self._save_models_cache(provider_type, models)
            return models

        # Fallback to cached or hardcoded
        if prov.models:
            logger.warning(f"Using stale model cache for {provider_type}")
            return prov.models
        if provider_type in _HARDCODED_MODELS:
            return _HARDCODED_MODELS[provider_type]
        return []

    def _fetch_models(self, provider_type: str, api_key: str) -> list[str]:
        """Fetch models from provider API."""
        endpoint = _MODEL_ENDPOINTS.get(provider_type)
        if not endpoint:
            return _HARDCODED_MODELS.get(provider_type, [])

        try:
            req = urllib.request.Request(endpoint)
            if api_key:
                if provider_type == "google":
                    # Google uses query param
                    endpoint = f"{endpoint}?key={api_key}"
                    req = urllib.request.Request(endpoint)
                else:
                    req.add_header("Authorization", f"Bearer {api_key}")

            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            # Parse response based on provider format
            return self._parse_models_response(provider_type, data)
        except Exception as e:
            logger.warning(f"Model discovery failed for {provider_type}: {e}")
            return []

    def _parse_models_response(self, provider_type: str, data: dict) -> list[str]:
        """Parse model list from API response."""
        models = []

        if provider_type == "openai":
            for m in data.get("data", []):
                mid = m.get("id", "")
                # Filter to chat models
                if "gpt" in mid or "o1" in mid or "o3" in mid:
                    models.append(mid)

        elif provider_type == "openrouter":
            for m in data.get("data", []):
                mid = m.get("id", "")
                if mid:
                    models.append(mid)

        elif provider_type == "google":
            for m in data.get("models", []):
                name = m.get("name", "")
                # Format: models/gemini-1.5-pro -> gemini-1.5-pro
                if name.startswith("models/"):
                    models.append(name[7:])
                elif name:
                    models.append(name)

        elif provider_type in ("kyma", "zai"):
            for m in data.get("data", []):
                mid = m.get("id", "")
                if mid:
                    models.append(mid)

        return models

    def can_use_model(
        self, provider_type: str, api_key: str, model: str
    ) -> tuple[bool, str]:
        """Check if a model is available on the provider.

        Returns: (can_use, reason)
        """
        models = self.get_available_models(provider_type, api_key)
        if not models:
            # No model list — assume available (fail at runtime)
            return True, "no_model_list"
        if model in models:
            return True, "available"
        # Check partial match (e.g., "gpt-4" matches "gpt-4-turbo")
        for m in models:
            if model in m or m in model:
                return True, f"partial_match:{m}"
        return False, "not_found"

    # -------------------------------------------------------------------------
    # Combined Status
    # -------------------------------------------------------------------------

    def get_provider_status(self, provider_type: str, api_key: str = "") -> dict:
        """Get full status for a provider."""
        prov = self._providers.get(provider_type)
        key_hash = self._hash_key(api_key) if api_key else None

        rate_limit = None
        if prov and key_hash and key_hash in prov.rate_limits:
            rate_limit = prov.rate_limits[key_hash].to_dict()

        models = self.get_available_models(provider_type, api_key) if api_key else []

        return {
            "provider": provider_type,
            "models_count": len(models),
            "models": models[:20],  # Limit for response size
            "models_updated_at": prov.models_updated_at if prov else None,
            "rate_limit": rate_limit,
            "quota_low": self.is_quota_low(provider_type, api_key) if api_key else None,
        }

    def get_all_statuses(self, api_keys: dict[str, str] = None) -> dict:
        """Get status for all known providers.

        Args:
            api_keys: Dict of provider_type -> api_key for rate limit lookup
        """
        api_keys = api_keys or {}
        result = {}
        for ptype in set(list(_MODEL_ENDPOINTS.keys()) + list(self._providers.keys())):
            api_key = api_keys.get(ptype, "")
            result[ptype] = self.get_provider_status(ptype, api_key)
        return result

    def get_usable_fallbacks(
        self, provider_type: str, api_key: str, exclude_models: set[str] = None
    ) -> list[dict]:
        """Get list of usable fallback models with quota info.

        Returns models sorted by quota remaining (highest first).
        """
        exclude_models = exclude_models or set()
        models = self.get_available_models(provider_type, api_key)
        status = self.get_rate_limit(provider_type, api_key)

        result = []
        for model in models:
            if model in exclude_models:
                continue
            result.append({
                "model": model,
                "provider": provider_type,
                "quota_pct": status.min_pct if status else None,
                "quota_low": self.is_quota_low(provider_type, api_key),
            })
        return result

    def refresh_all(self, api_keys: dict[str, str] = None) -> dict:
        """Force refresh model lists for all providers."""
        api_keys = api_keys or {}
        result = {}
        for ptype in _MODEL_ENDPOINTS:
            api_key = api_keys.get(ptype, "")
            models = self.get_available_models(ptype, api_key, force_refresh=True)
            result[ptype] = {"models_count": len(models), "models": models[:10]}
        return result


def get_provider_status_manager() -> ProviderStatusManager:
    """Get singleton instance."""
    return ProviderStatusManager()
