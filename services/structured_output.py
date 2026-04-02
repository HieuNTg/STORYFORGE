"""Structured output helper — wraps LLM calls to return validated JSON dicts.

Uses response_format json_object for OpenAI-compatible providers.
Falls back to regex JSON extraction for Anthropic, Gemini, Ollama, and custom endpoints.
Schema validation is lightweight: checks that all expected keys are present in the response.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Providers that natively support response_format: {type: "json_object"}
_JSON_MODE_PROVIDERS = {"openai", "openrouter", "custom"}

# Regex to extract the first {...} JSON block from free-form text
_JSON_BLOCK_RE = re.compile(r"\{[\s\S]*\}", re.MULTILINE)


def _detect_provider(base_url: str) -> str:
    """Detect provider from base URL (mirrors services/llm/retry._detect_provider)."""
    if not base_url:
        return "openai"
    url = base_url.lower()
    if "openrouter" in url:
        return "openrouter"
    if "localhost" in url or "127.0.0.1" in url or "ollama" in url:
        return "ollama"
    if "anthropic" in url:
        return "anthropic"
    if "gemini" in url or "googleapis" in url:
        return "google"
    if "api.openai.com" in url:
        return "openai"
    return "custom"


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from text, repairing minor issues."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Extract first {...} block
    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            # Last resort: strip trailing commas before closing braces/brackets
            cleaned = re.sub(r",\s*([\}\]])", r"\1", match.group())
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

    raise ValueError(f"No valid JSON object found in LLM response: {text[:200]!r}")


def _validate_schema(data: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return list of missing required keys (schema is a dict of expected top-level keys)."""
    return [key for key in schema if key not in data]


def generate_structured(
    prompt: str,
    schema: dict[str, Any],
    *,
    system_prompt: str = "You are a helpful assistant. Always respond with valid JSON.",
    temperature: float = 0.2,
    max_tokens: int = 1024,
    model_tier: str = "default",
    strict: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    """Generate a structured JSON response from the LLM.

    Detects provider from config and uses json_object mode where supported.
    Falls back to regex extraction for providers that don't support it.

    Args:
        prompt: User-facing prompt describing the task.
        schema: Dict whose keys define required output fields (values are ignored —
                only key presence is validated). E.g. {"title": ..., "score": ...}
        system_prompt: Override the default system instruction.
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Max tokens in the response.
        model_tier: "default" | "cheap" — passed through to LLMClient.
        strict: If True, raises ValueError when required keys are missing.
        **kwargs: Extra keyword args forwarded to LLMClient.generate().

    Returns:
        Parsed dict from the LLM response.

    Raises:
        ValueError: If JSON extraction fails or strict=True with missing keys.
    """
    from services.llm_client import LLMClient
    from config import ConfigManager

    config = ConfigManager()
    base_url = config.llm.base_url or ""
    provider = _detect_provider(base_url)
    use_json_mode = provider in _JSON_MODE_PROVIDERS

    client = LLMClient()

    if use_json_mode:
        # Native JSON mode — provider enforces well-formed JSON output
        logger.debug("generate_structured: using json_object mode (provider=%s)", provider)
        raw = client.generate(
            system_prompt=system_prompt,
            user_prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            model_tier=model_tier,
            **kwargs,
        )
    else:
        # Regex fallback — add JSON instruction to prompt
        logger.debug("generate_structured: using regex extraction (provider=%s)", provider)
        json_hint = (
            "\n\nIMPORTANT: Your response must be a single valid JSON object with no "
            "surrounding text, markdown, or code fences."
        )
        raw = client.generate(
            system_prompt=system_prompt + json_hint,
            user_prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,
            model_tier=model_tier,
            **kwargs,
        )

    # Parse and validate
    data = _extract_json(raw)

    missing = _validate_schema(data, schema)
    if missing:
        msg = f"generate_structured: response missing keys {missing}"
        if strict:
            raise ValueError(msg)
        logger.warning(msg)

    return data
