"""Regression test: a connection ping must give the model room to answer.

Observed on 2026-08-26: the provider card for Google Gemini showed "Lỗi kết
nối" while the log showed `generateContent "HTTP/1.1 200 OK"`. The ping asked
for max_tokens=5; gemma-4-31b-it is a thinking model and `max_output_tokens`
covers its thoughts, so it burned the cap before emitting any text. The
provider raised "LLM returned empty content" and a healthy provider was
reported as unreachable.

Measured on that model: 5 tokens → 2 thought tokens, no text; 64 → 61 thought
tokens, still no text; 256 → 114 thought tokens then "pong!". Hence a ping
budget in the hundreds, not the dozens.
"""

from services.llm.generation import _PING_MAX_TOKENS, GenerationMixin


class _RecordingProvider:
    """Fails the way a real provider does when the output cap is too small."""

    def __init__(self, min_tokens_to_answer: int):
        self.min_tokens_to_answer = min_tokens_to_answer
        self.seen_max_tokens = None

    def complete(self, messages, model, temperature, max_tokens, **kwargs):
        self.seen_max_tokens = max_tokens
        if max_tokens < self.min_tokens_to_answer:
            raise RuntimeError(f"LLM returned empty content (model={model})")
        return "OK"


class _Checker(GenerationMixin):
    """Bare host for the mixin — check_provider needs nothing else."""


def _check(monkeypatch, provider):
    import services.llm.providers as providers_mod

    monkeypatch.setattr(providers_mod, "get_provider", lambda **kw: provider)
    return _Checker().check_provider("https://api.example.com/v1", "k", "some-model")


class TestPingBudget:
    def test_ping_clears_a_thinking_models_budget(self):
        # gemma-4-31b-it spent 114 tokens thinking before its first character.
        assert _PING_MAX_TOKENS >= 200

    def test_model_that_needs_room_now_passes(self, monkeypatch):
        provider = _RecordingProvider(min_tokens_to_answer=128)
        ok, msg = _check(monkeypatch, provider)
        assert (ok, msg) == (True, "OK")
        assert provider.seen_max_tokens == _PING_MAX_TOKENS

    def test_genuinely_broken_provider_still_fails(self, monkeypatch):
        # A provider that cannot answer at any budget must stay a failure —
        # the fix widens the ping, it does not paper over real errors.
        provider = _RecordingProvider(min_tokens_to_answer=10_000)
        ok, msg = _check(monkeypatch, provider)
        assert ok is False
        assert "empty content" in msg
