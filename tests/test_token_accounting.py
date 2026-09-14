"""Sprint 2 — cost accounting must reflect what was actually spent.

Three defects made every cost figure and every budget cap wrong:

1. Providers reported exact token counts and the client threw them away.
2. The fallback estimate was `len(text) // 4`, which runs far below the real
   count for Vietnamese prose — so caps fired long after the spend they bound.
3. The streaming path, which carries the chapter body and is the largest token
   consumer in a run, was invisible to the wallet and the trace entirely.
"""

from unittest.mock import MagicMock, patch

import pytest

from services.llm.client import _estimate_tokens
from services.llm.providers.base import capture_usage


VI_SAMPLE = (
    "Lan bước vào khu rừng, tiếng lá xào xạc dưới chân nàng, "
    "mùi đất ẩm bốc lên nồng nàn. " * 10
)


class TestVietnameseAwareEstimation:
    def test_estimate_is_well_above_the_old_len_over_four(self):
        """The old heuristic under-counted Vietnamese by roughly half."""
        old = len(VI_SAMPLE) // 4
        assert _estimate_tokens(VI_SAMPLE) > old * 1.5

    def test_empty_text_is_zero(self):
        assert _estimate_tokens("") == 0

    def test_ascii_text_stays_reasonable(self):
        """The fix must not wildly inflate plain English either."""
        text = "The quick brown fox jumps over the lazy dog. " * 20
        est = _estimate_tokens(text)
        assert len(text) // 8 < est < len(text)


class TestProviderUsageCapture:
    def test_openai_shaped_usage_is_captured(self):
        out: dict = {}
        capture_usage(out, MagicMock(prompt_tokens=120, completion_tokens=340))
        assert out == {"prompt_tokens": 120, "completion_tokens": 340}

    def test_anthropic_field_names(self):
        out: dict = {}
        capture_usage(
            out,
            MagicMock(input_tokens=11, output_tokens=22),
            prompt_attr="input_tokens",
            completion_attr="output_tokens",
        )
        assert out == {"prompt_tokens": 11, "completion_tokens": 22}

    def test_missing_usage_is_a_noop(self):
        out: dict = {}
        capture_usage(out, None)
        assert out == {}

    def test_no_output_dict_is_a_noop(self):
        capture_usage(None, MagicMock(prompt_tokens=1, completion_tokens=2))

    def test_partial_usage_records_what_it_has(self):
        out: dict = {}
        usage = MagicMock(prompt_tokens=50)
        usage.completion_tokens = None
        capture_usage(out, usage)
        assert out == {"prompt_tokens": 50}


class TestProvidersFillUsage:
    def test_openai_provider_fills_usage_out(self):
        from services.llm.providers.openai_provider import OpenAIProvider

        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "nội dung"
        response.usage = MagicMock(prompt_tokens=7, completion_tokens=9)

        client = MagicMock()
        client.chat.completions.create.return_value = response

        with patch("openai.OpenAI", return_value=client):
            provider = OpenAIProvider(api_key="k", base_url="https://x/v1")

        usage: dict = {}
        provider.complete([{"role": "user", "content": "hi"}], "m", 0.5, 100, False, usage)

        assert usage == {"prompt_tokens": 7, "completion_tokens": 9}

    def test_usage_dict_is_per_call_not_shared(self):
        """Concurrent chapters must not see each other's counts."""
        from services.llm.providers.openai_provider import OpenAIProvider

        response = MagicMock()
        response.choices = [MagicMock()]
        response.choices[0].message.content = "x"
        response.usage = MagicMock(prompt_tokens=1, completion_tokens=1)
        client = MagicMock()
        client.chat.completions.create.return_value = response
        with patch("openai.OpenAI", return_value=client):
            provider = OpenAIProvider(api_key="k", base_url="https://x/v1")

        a: dict = {}
        b: dict = {}
        provider.complete([], "m", 0.5, 10, False, a)
        response.usage = MagicMock(prompt_tokens=99, completion_tokens=99)
        provider.complete([], "m", 0.5, 10, False, b)

        assert a == {"prompt_tokens": 1, "completion_tokens": 1}
        assert b == {"prompt_tokens": 99, "completion_tokens": 99}


class TestStreamingIsCosted:
    def _client(self):
        from services.llm.generation import GenerationMixin

        return GenerationMixin()

    def test_stream_records_a_trace_call(self):
        charged = {}

        def fake_record(**kwargs):
            charged.update(kwargs)

        with patch("services.llm.client._record_trace_call", fake_record), patch(
            "services.llm.client.LLMClient.charge_wallet"
        ):
            self._client()._account_for_stream(
                model="m",
                label="primary:m",
                messages=[{"role": "user", "content": "viết chương"}],
                text=VI_SAMPLE,
                duration_ms=1234,
            )

        assert charged["success"] is True
        assert charged["usage"]["completion_tokens"] > 0

    def test_stream_charges_the_wallet(self):
        with patch("services.llm.client._record_trace_call"), patch(
            "services.llm.client.LLMClient.charge_wallet"
        ) as wallet:
            self._client()._account_for_stream(
                model="m",
                label="primary:m",
                messages=[{"role": "user", "content": "viết chương"}],
                text=VI_SAMPLE,
                duration_ms=10,
            )

        wallet.assert_called_once()
        _cost, tokens = wallet.call_args[0][:2]
        assert tokens > 0, "the streamed body must count toward the budget"

    def test_budget_exception_propagates(self):
        """A cap breach must abort the run, not be swallowed as telemetry."""
        from services.llm.client import LLMBudgetExceededError

        with patch("services.llm.client._record_trace_call"), patch(
            "services.llm.client.LLMClient.charge_wallet",
            side_effect=LLMBudgetExceededError("cap"),
        ):
            with pytest.raises(LLMBudgetExceededError):
                self._client()._account_for_stream(
                    model="m",
                    label="primary:m",
                    messages=[],
                    text="x",
                    duration_ms=1,
                )

    def test_telemetry_failure_does_not_break_generation(self):
        with patch(
            "services.llm.client._record_trace_call", side_effect=RuntimeError("boom")
        ), patch("services.llm.client.LLMClient.charge_wallet"):
            # Must not raise: a broken trace sink cannot cost the user their story.
            self._client()._account_for_stream(
                model="m", label="", messages=[], text="x", duration_ms=1
            )
