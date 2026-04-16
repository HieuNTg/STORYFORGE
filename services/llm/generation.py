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
        text = self._generate_json_text(
            system_prompt, user_prompt, temperature, max_tokens,
            model_tier, model,
        )

        # Attempt 1: direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed, attempting repair: {e}")

        # Attempt 2: repair common issues (trailing commas, quotes, truncation)
        repaired = _repair_json(text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            pass

        # Attempt 3: ask LLM to fix (use cheap model) — skip if text is trivially short
        if len(text) < 5:
            raise ValueError(
                f"JSON parse failed: LLM returned near-empty response "
                f"({len(text)} chars): {text!r}"
            )
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

    def _generate_json_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: Optional[float],
        max_tokens: Optional[int],
        model_tier: str,
        model: Optional[str],
        _retried: bool = False,
    ) -> str:
        """Generate text for JSON parsing, retrying once on empty response."""
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

        # Retry once on empty — likely a flaky free model
        if not text and not _retried:
            logger.warning("LLM returned empty response for JSON request, retrying")
            return self._generate_json_text(
                system_prompt, user_prompt, temperature, max_tokens,
                model_tier, model, _retried=True,
            )

        # Strip markdown code block
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        return text

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
            self._stream_with_retry(_api_gen, "API stream"),
            chunk_timeout=30,
            first_chunk_timeout=60,
        )

    def check_connection(self) -> tuple[bool, str]:
        """Check API backend connection using full fallback chain."""
        try:
            self.generate(
                system_prompt="Reply OK",
                user_prompt="ping",
                temperature=0.0,
                max_tokens=5,
            )
            return True, "Kết nối thành công"
        except Exception as e:
            return False, f"Lỗi kết nối: {str(e)}"

    def check_provider(self, base_url: str, api_key: str, model: str) -> tuple[bool, str]:
        """Check connection to a specific provider."""
        from services.llm.providers import get_provider
        try:
            provider = get_provider(base_url=base_url, api_key=api_key)
            provider.complete(
                messages=[{"role": "user", "content": "ping"}],
                model=model, temperature=0.0, max_tokens=5,
            )
            return True, "OK"
        except Exception as e:
            return False, str(e)[:200]


def _repair_json(text: str) -> str:
    """Fix common JSON issues: trailing commas, single quotes, truncation."""
    if not text or len(text) < 2:
        return text
    text = re.sub(r',\s*([}\]])', r'\1', text)
    text = re.sub(r"(?<=[\[{,:])\s*'([^']*?)'\s*(?=[,}\]:])", r' "\1" ', text)
    # Extract JSON boundaries
    starts = [text.find(c) for c in ('{', '[') if text.find(c) >= 0]
    ends = [text.rfind(c) for c in ('}', ']') if text.rfind(c) >= 0]
    if starts and ends:
        text = text[min(starts):max(ends) + 1]
    elif starts:
        # Truncated — no closing bracket found; attempt to close
        text = text[min(starts):]
        text = _close_truncated_json(text)
    return text


def _close_truncated_json(text: str) -> str:
    """Best-effort closure of truncated JSON by balancing brackets/quotes."""
    in_string = False
    escape = False
    stack = []
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append('}' if ch == '{' else ']')
        elif ch in ('}', ']'):
            if stack:
                stack.pop()
    # Close unclosed string
    if in_string:
        text += '"'
    # Remove trailing comma before we close
    text = re.sub(r',\s*$', '', text)
    # Close unclosed brackets in reverse order
    text += ''.join(reversed(stack))
    return text
