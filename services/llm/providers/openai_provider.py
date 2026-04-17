"""OpenAI-compatible provider (OpenAI, OpenRouter, vLLM, LM Studio, etc.)."""
import logging
from typing import Iterator

logger = logging.getLogger(__name__)


def _detect_provider_type(base_url: str) -> str:
    """Detect provider type from URL for rate limit tracking."""
    if not base_url:
        return "openai"
    url = base_url.lower()
    if "openrouter" in url:
        return "openrouter"
    if "kymaapi.com" in url:
        return "kyma"
    if "api.openai.com" in url:
        return "openai"
    if "z.ai" in url:
        return "zai"
    return "generic"


class OpenAIProvider:
    _is_llm_provider = True

    def __init__(self, api_key: str, base_url: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self._base_url = base_url
        self._api_key = api_key
        self._provider_type = _detect_provider_type(base_url)

    @property
    def base_url(self):
        return self._base_url

    def _extract_rate_limits(self, response) -> None:
        """Extract rate limit headers from response and report to status manager."""
        try:
            # OpenAI SDK stores raw httpx response in _response attribute
            raw_response = getattr(response, "_response", None)
            if not raw_response:
                return
            headers = dict(raw_response.headers) if hasattr(raw_response, "headers") else {}
            if not headers:
                return
            from services.llm.provider_status import get_provider_status_manager
            mgr = get_provider_status_manager()
            mgr.extract_rate_limits(self._provider_type, self._api_key, headers)
        except Exception as e:
            logger.debug(f"Rate limit extraction failed: {e}")

    def complete(self, messages: list[dict], model: str, temperature: float,
                 max_tokens: int, json_mode: bool = False) -> str:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        self._extract_rate_limits(response)
        if not response.choices:
            raise RuntimeError(f"LLM returned empty choices (model={model}, finish_reason=unknown)")
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError(
                f"LLM returned empty content (model={model}, "
                f"finish_reason={response.choices[0].finish_reason})"
            )
        return content

    def stream(self, messages: list[dict], model: str, temperature: float,
               max_tokens: int) -> Iterator[str]:
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
