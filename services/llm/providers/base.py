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
        usage_out: dict | None = None,
    ) -> str:
        """Return the completion text.

        `usage_out`, when given, is filled with the provider's own token counts
        (`prompt_tokens` / `completion_tokens`). Callers pass a fresh dict per
        call, so nothing is shared between concurrent chapters. Costs were
        previously derived from len(text)//4, which under-counts Vietnamese by
        roughly 45% and made every budget cap fire far too late.
        """
        ...

    def stream(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> Iterator[str]: ...


def capture_usage(usage_out, raw_usage, *, prompt_attr="prompt_tokens", completion_attr="completion_tokens") -> None:
    """Copy a provider's own token counts into `usage_out`, if both exist.

    Every SDK reports exact counts and StoryForge threw them away, estimating
    instead with len(text)//4 — about 45% low for Vietnamese prose, so cost
    caps triggered long after the spend they were meant to bound.
    """
    if usage_out is None or raw_usage is None:
        return
    try:
        prompt = getattr(raw_usage, prompt_attr, None)
        completion = getattr(raw_usage, completion_attr, None)
        if prompt is not None:
            usage_out["prompt_tokens"] = int(prompt)
        if completion is not None:
            usage_out["completion_tokens"] = int(completion)
    except (TypeError, ValueError):  # pragma: no cover - defensive
        pass
