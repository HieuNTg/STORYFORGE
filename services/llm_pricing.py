"""LLM pricing table (USD per 1M tokens). Update quarterly against invoices.

Provider rate-card sources (verify before quoting costs publicly):
- Anthropic: https://www.anthropic.com/pricing
- OpenAI:    https://openai.com/pricing
- Google:    https://ai.google.dev/pricing
- Z.AI:      free tier as of 2026-04
"""
from __future__ import annotations

# USD per 1M tokens
PRICING: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-opus-4-7":     {"input": 15.00, "output": 75.00},
    "claude-opus-4-6":     {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":   {"input":  3.00, "output": 15.00},
    "claude-haiku-4-5":    {"input":  0.25, "output":  1.25},
    # OpenAI
    "gpt-5-opus":          {"input": 15.00, "output": 75.00},
    "gpt-5":               {"input":  3.00, "output": 15.00},
    "gpt-5-mini":          {"input":  0.25, "output":  1.25},
    "gpt-5-nano":          {"input":  0.05, "output":  0.25},
    "gpt-4o":              {"input":  2.50, "output": 10.00},
    "gpt-4o-mini":         {"input":  0.15, "output":  0.60},
    # Google
    "gemini-2.5-pro":      {"input":  1.25, "output":  5.00},
    "gemini-2.5-flash":    {"input":  0.15, "output":  0.60},
    "gemini-2.0-flash":    {"input":  0.10, "output":  0.40},
    # Z.AI (free tier)
    "glm-4.6":             {"input":  0.00, "output":  0.00},
    "glm-4.5":             {"input":  0.00, "output":  0.00},
    # Fallback for unknown models
    "_default":            {"input":  1.00, "output":  3.00},
}


def compute_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """USD cost for a single LLM call. Returns 0.0 for non-positive token counts."""
    if prompt_tokens < 0 or completion_tokens < 0:
        return 0.0
    rates = _resolve_rates(model)
    return (
        prompt_tokens * rates["input"] + completion_tokens * rates["output"]
    ) / 1_000_000


def _resolve_rates(model: str) -> dict[str, float]:
    if not model:
        return PRICING["_default"]
    if model in PRICING:
        return PRICING[model]
    # Prefix match (e.g. "claude-opus-4-7-20250101" → "claude-opus-4-7")
    for key in PRICING:
        if key == "_default":
            continue
        if model.startswith(key):
            return PRICING[key]
    return PRICING["_default"]
