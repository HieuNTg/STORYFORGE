"""Base protocol for LLM providers."""
from typing import Iterator, Protocol


class LLMProvider(Protocol):
    """Protocol that all LLM providers must implement."""

    def complete(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str: ...

    def stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]: ...
