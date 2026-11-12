"""Provider API-key detection from config.

Extracted verbatim from api/provider_status_routes.py so the route module
stays thin. Maps the configured base_url (primary + fallback_models) to a
provider type and fills gaps from well-known environment variables.
"""

import ipaddress
import logging
import os
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Provider keys the fallback chain picks up from the environment.
_ENV_KEYS = ("ANTHROPIC_API_KEY", "GOOGLE_AI_API_KEY", "ZAI_API_KEY")
_LOCAL_NAMES = {"localhost", "host.docker.internal"}


def get_api_keys_from_config() -> dict[str, str]:
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


def _is_local_endpoint(base_url: str) -> bool:
    """True for a model server on this machine or the LAN, which may need no key:
    loopback names and IPs, ``host.docker.internal``, private/link-local IPs."""
    host = (urlparse(base_url or "").hostname or "").lower().rstrip(".")
    if not host:
        return False
    if host in _LOCAL_NAMES:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _pool_key(item) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("key") or item.get("api_key") or ""
    return ""


def has_usable_llm_key(llm) -> bool:
    """False only when generation cannot authenticate anywhere.

    Any non-empty key counts (primary, layer 1/2, the ``api_keys`` pool, a
    fallback profile, a provider key from the environment), and so does any
    endpoint on this machine or the LAN (local Ollama / LM Studio need no key).
    Deliberately permissive: it exists to turn the first run without a key
    into a clear message, not to second-guess a configured setup.
    """
    if any(
        getattr(llm, f, "") for f in ("api_key", "layer1_api_key", "layer2_api_key")
    ):
        return True
    if any(_pool_key(item) for item in getattr(llm, "api_keys", None) or []):
        return True
    fallbacks = [fb for fb in getattr(llm, "fallback_models", None) or [] if isinstance(fb, dict)]
    if any(fb.get("api_key") for fb in fallbacks):
        return True
    if any(os.environ.get(k, "").strip() for k in _ENV_KEYS):
        return True
    urls = [
        getattr(llm, f, "") or ""
        for f in ("base_url", "layer1_base_url", "layer2_base_url", "cheap_base_url")
    ] + [fb.get("base_url") or "" for fb in fallbacks]
    return any(_is_local_endpoint(u) for u in urls)


def ensure_llm_key() -> None:
    """Route dependency: raise ``ApiKeyMissing`` (400 ``api_key_missing``)
    before a run starts when no usable key exists."""
    from config import ConfigManager
    from errors.exceptions import ApiKeyMissing

    if not has_usable_llm_key(ConfigManager().llm):
        raise ApiKeyMissing()
