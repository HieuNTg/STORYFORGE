"""Generation mixins — JSON parsing, streaming, and connection check for LLMClient."""

import json
import logging
import re
from typing import Optional


logger = logging.getLogger(__name__)


def _config_manager():
    """Lazy-resolve ConfigManager through compat hub for test mock support."""
    import services.llm_client as m
    return m.ConfigManager


class GenerationMixin:
    """Mixin providing generate_json, generate_stream, and check_connection."""

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model_tier: str = "default",
        model: Optional[str] = None,
    ) -> dict:
        """Call LLM and parse JSON result with auto-repair."""
        result = self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            model_tier=model_tier,
            model=model,
        )
        text = result.strip()
        # Strip markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        # Attempt 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed, attempting repair: {e}")

        # Attempt 2: repair common issues
        repaired = _repair_json(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Attempt 3: ask LLM to fix (use cheap model)
        logger.warning("JSON repair failed, asking LLM to fix")
        fixed = self.generate(
            system_prompt="Fix this malformed JSON. Return ONLY valid JSON, no explanation.",
            user_prompt=text[:4000],
            temperature=0.0,
            json_mode=True,
            model_tier="cheap",
        )
        try:
            return json.loads(fixed)
        except json.JSONDecodeError as e:
            preview = fixed[:800] if fixed else "<empty>"
            raise ValueError(
                f"JSON parse failed after 3 attempts. "
                f"Parse error: {e}. "
                f"Last text ({len(fixed)} chars, showing first 800): {preview!r}"
            ) from e

    def generate_stream(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model_tier: str = "default",
        model: Optional[str] = None,
    ):
        """Call LLM with streaming."""
        config = _config_manager()()
        effective_temp = temperature if temperature is not None else config.llm.temperature

        from services.prompts import localize_prompt
        lang = config.pipeline.language
        system_prompt = localize_prompt(system_prompt, lang)
        user_prompt = localize_prompt(user_prompt, lang)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if model_tier == "cheap" and config.llm.cheap_model:
            provider, effective_model = self._get_cheap_client()
        else:
            provider = self._get_client()
            effective_model = model or self._current_model or config.llm.model

        eff_max_tokens = max_tokens or config.llm.max_tokens

        def _api_gen():
            yield from provider.stream(messages, effective_model, effective_temp, eff_max_tokens)

        yield from self._stream_with_chunk_timeout(
            self._stream_with_retry(_api_gen, "API stream"), chunk_timeout=60
        )

    def check_connection(self) -> tuple[bool, str]:
        """Check API backend connection."""
        try:
            provider = self._get_client()
            model = self._current_model or _config_manager()().llm.model
            messages = [{"role": "user", "content": "test"}]
            # Use the LLMProvider protocol (.complete) when available.
            # Fall back to raw OpenAI SDK (.chat.completions.create) when
            # _get_client() was monkey-patched to return a raw client (tests).
            _is_provider = getattr(type(provider), "_is_llm_provider", False)
            if _is_provider:
                provider.complete(
                    messages=messages,
                    model=model,
                    temperature=0.0,
                    max_tokens=5,
                )
            else:
                provider.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=5,
                )
            return True, "Kết nối thành công"
        except Exception as e:
            return False, f"Lỗi kết nối: {str(e)}"


def _repair_json(text: str) -> str:
    """Fix common JSON issues."""
    text = re.sub(r',\s*([}\]])', r'\1', text)
    text = re.sub(r"(?<=[\[{,:])\s*'([^']*?)'\s*(?=[,}\]:])", r' "\1" ', text)
    starts = [text.find(c) for c in ('{', '[') if text.find(c) >= 0]
    ends = [text.rfind(c) for c in ('}', ']') if text.rfind(c) >= 0]
    if starts and ends:
        return text[min(starts):max(ends) + 1]
    return text
