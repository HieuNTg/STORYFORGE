"""Generation mixins — JSON parsing, streaming, and connection check for LLMClient."""

import json
import logging
import re
from typing import Optional

from services.llm.retry import MAX_RETRIES, WebBackendExhausted, _redact

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
    ) -> dict:
        """Call LLM and parse JSON result with auto-repair."""
        result = self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            model_tier=model_tier,
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
    ):
        """Call LLM with streaming. Supports API and web backend."""
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

        # Web backend streaming
        if self._is_web_backend():
            def _web_gen():
                web_client = self._get_web_client()
                yield from web_client.chat_completion(
                    messages=messages, temperature=effective_temp, stream=True,
                )
            yield from self._stream_with_chunk_timeout(
                self._stream_with_retry(_web_gen, "Web stream"), chunk_timeout=60
            )
            return

        # API backend streaming
        if model_tier == "cheap" and config.llm.cheap_model:
            client, effective_model = self._get_cheap_client()
        else:
            client = self._get_client()
            effective_model = self._current_model or config.llm.model

        kwargs = {
            "model": effective_model,
            "messages": messages,
            "temperature": effective_temp,
            "max_tokens": max_tokens or config.llm.max_tokens,
            "stream": True,
        }

        def _api_gen():
            response = client.chat.completions.create(**kwargs)
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        yield from self._stream_with_chunk_timeout(
            self._stream_with_retry(_api_gen, "API stream"), chunk_timeout=60
        )

    def check_connection(self) -> tuple[bool, str]:
        """Check backend connection (API or web)."""
        if self._is_web_backend():
            try:
                web_client = self._get_web_client()
                return web_client.check_connection()
            except Exception as e:
                return False, f"Lỗi web backend: {e}"

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._current_model or _config_manager()().llm.model,
                messages=[{"role": "user", "content": "test"}],
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
