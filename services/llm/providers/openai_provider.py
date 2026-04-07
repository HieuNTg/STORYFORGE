"""OpenAI-compatible provider (OpenAI, OpenRouter, vLLM, LM Studio, etc.)."""
from typing import Iterator


class OpenAIProvider:
    _is_llm_provider = True

    def __init__(self, api_key: str, base_url: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self._base_url = base_url

    @property
    def base_url(self):
        return self._base_url

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
        if not response.choices:
            raise RuntimeError(f"LLM returned empty choices (model={model}, finish_reason=unknown)")
        return response.choices[0].message.content or ""

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
