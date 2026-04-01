"""Dedicated LLM client for long-context generation."""

import logging
import random
import time

from openai import OpenAI
from config import ConfigManager

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
BASE_DELAY = 1.0

_TRANSIENT_CODES = {429, 500, 502, 503, 504}


def _is_transient(exc: Exception) -> bool:
    exc_str = str(exc).lower()
    if any(str(code) in exc_str for code in _TRANSIENT_CODES):
        return True
    if any(kw in exc_str for kw in ("timeout", "connection", "reset", "broken pipe")):
        return True
    return False


class LongContextClient:
    """Non-singleton LLM client for long-context generation.

    Reads long_context_* fields from PipelineConfig.
    Uses OpenAI SDK for all providers.
    """

    def __init__(self):
        cfg = ConfigManager().pipeline
        self.provider = cfg.long_context_provider
        self.model = cfg.long_context_model
        self.api_key = cfg.long_context_api_key
        self.base_url = cfg.long_context_base_url
        self.max_context = cfg.long_context_max_tokens
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.provider and self.model and self.api_key)

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.api_key,
                base_url=self.base_url or None,
            )
        return self._client

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.8,
        max_tokens: int = 8192,
    ) -> str:
        """Generate text using the long-context model with retry logic."""
        if not self.is_configured:
            raise RuntimeError("LongContextClient is not configured (missing provider/model/api_key)")

        # Apply language localization (same as LLMClient.generate)
        from services.prompts import localize_prompt
        lang = ConfigManager().pipeline.language
        system_prompt = localize_prompt(system_prompt, lang)
        user_prompt = localize_prompt(user_prompt, lang)

        client = self._get_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                result = response.choices[0].message.content or ""
                logger.info(f"LongContextClient success via {self.provider}/{self.model}")
                return result
            except Exception as e:
                last_exc = e
                if attempt < MAX_RETRIES - 1 and _is_transient(e):
                    delay = BASE_DELAY * (2 ** attempt) + random.uniform(0, 0.5)
                    logger.warning(
                        f"LongContextClient attempt {attempt + 1} failed: {e}. Retry in {delay:.1f}s"
                    )
                    time.sleep(delay)
                    continue
                break

        raise last_exc
