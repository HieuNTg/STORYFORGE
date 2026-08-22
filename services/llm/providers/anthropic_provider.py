"""Native Anthropic provider."""

import logging
from typing import Iterator

logger = logging.getLogger(__name__)


class AnthropicProvider:
    _is_llm_provider = True

    def __init__(self, api_key: str, base_url: str = "", timeout: float | None = None):
        try:
            from anthropic import Anthropic

            from services.llm.providers.openai_provider import _config_timeout

            kwargs: dict = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            # Same policy as OpenAIProvider: honour llm.request_timeout, and
            # disable the SDK's own retries. The Anthropic SDK defaults to two
            # internal retries, which multiplied against our retry loop and the
            # fallback chain — the exact stacking the OpenAI provider avoids.
            kwargs["timeout"] = (
                timeout if timeout and timeout > 0 else _config_timeout()
            )
            kwargs["max_retries"] = 0
            self.client = Anthropic(**kwargs)
            self._base_url = base_url
            self._api_key = api_key
        except ImportError:
            raise ImportError("Anthropic SDK not installed. Run: pip install anthropic")

    @property
    def base_url(self):
        return self._base_url

    def _extract_rate_limits(self, response) -> None:
        """Extract rate limit headers from response."""
        try:
            # Anthropic SDK exposes headers via response._request_id or raw response
            raw_response = getattr(response, "_response", None)
            if not raw_response:
                return
            headers = (
                dict(raw_response.headers) if hasattr(raw_response, "headers") else {}
            )
            if not headers:
                return
            from services.llm.provider_status import get_provider_status_manager

            mgr = get_provider_status_manager()
            mgr.extract_rate_limits("anthropic", self._api_key, headers)
        except Exception as e:
            logger.debug(f"Rate limit extraction failed: {e}")

    def _split_messages(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Extract system prompt and filter to user/assistant messages."""
        system_msg = ""
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_messages.append(m)
        return system_msg, user_messages

    def complete(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
        usage_out: dict | None = None,
    ) -> str:
        system_msg, user_messages = self._split_messages(messages)
        kwargs: dict = {
            "model": model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_msg:
            kwargs["system"] = system_msg
        response = self.client.messages.create(**kwargs)
        self._extract_rate_limits(response)
        from services.llm.providers.base import capture_usage

        # Anthropic names them input_tokens / output_tokens.
        capture_usage(
            usage_out,
            getattr(response, "usage", None),
            prompt_attr="input_tokens",
            completion_attr="output_tokens",
        )
        content = response.content[0].text
        if not content or not content.strip():
            raise RuntimeError(f"LLM returned empty content (model={model})")
        return content

    def stream(
        self, messages: list[dict], model: str, temperature: float, max_tokens: int
    ) -> Iterator[str]:
        system_msg, user_messages = self._split_messages(messages)
        kwargs: dict = {
            "model": model,
            "messages": user_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_msg:
            kwargs["system"] = system_msg
        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text
