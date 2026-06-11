"""Provider API-key detection from config.

Extracted verbatim from api/provider_status_routes.py so the route module
stays thin. Maps the configured base_url (primary + fallback_models) to a
provider type and fills gaps from well-known environment variables.
"""

import logging

logger = logging.getLogger(__name__)


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
