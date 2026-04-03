"""LLM provider factory with URL-based auto-detection."""
from .base import LLMProvider
from .openai_provider import OpenAIProvider


def get_provider(base_url: str, api_key: str) -> LLMProvider:
    """Auto-detect and return the appropriate LLM provider.

    Detects Anthropic and Google Gemini native endpoints by URL pattern.
    Falls back to OpenAI-compatible for everything else (OpenAI, OpenRouter,
    Ollama, vLLM, LM Studio, etc.).
    """
    url_lower = (base_url or "").lower()

    if "anthropic.com" in url_lower:
        from .anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=api_key, base_url=base_url)

    if "googleapis.com" in url_lower or "generativelanguage" in url_lower:
        from .gemini_provider import GeminiProvider
        return GeminiProvider(api_key=api_key, base_url=base_url)

    # Default: OpenAI-compatible
    return OpenAIProvider(api_key=api_key, base_url=base_url)


__all__ = ["LLMProvider", "OpenAIProvider", "get_provider"]
