"""Native Anthropic provider."""
from typing import Iterator


class AnthropicProvider:
    _is_llm_provider = True

    def __init__(self, api_key: str, base_url: str = ""):
        try:
            from anthropic import Anthropic
            kwargs: dict = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url
            self.client = Anthropic(**kwargs)
            self._base_url = base_url
        except ImportError:
            raise ImportError(
                "Anthropic SDK not installed. Run: pip install anthropic"
            )

    @property
    def base_url(self):
        return self._base_url

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

    def complete(self, messages: list[dict], model: str, temperature: float,
                 max_tokens: int, json_mode: bool = False) -> str:
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
        return response.content[0].text

    def stream(self, messages: list[dict], model: str, temperature: float,
               max_tokens: int) -> Iterator[str]:
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
