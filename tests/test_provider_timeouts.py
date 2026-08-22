"""Regression tests: llm.request_timeout must reach every provider.

Only OpenAIProvider honoured `llm.request_timeout` and disabled the SDK's own
retries. Anthropic kept its default two internal retries — multiplying against
our retry loop and the fallback chain, the exact stacking the OpenAI provider's
comment says it avoids — and Gemini used the SDK default timeout, so raising the
ceiling for slow local bridges had no effect on either.

The thresholds around it were self-contradictory too: the stream wrapper killed
a call at 180s and the fallback manager blacklisted any model averaging over
120s, both well inside the 900s the request timeout allows.
"""

from unittest.mock import MagicMock, patch

from config.defaults import LLMConfig, PipelineConfig


class TestAnthropicProviderTimeout:
    def test_timeout_and_no_sdk_retries(self):
        from services.llm.providers.anthropic_provider import AnthropicProvider

        fake_sdk = MagicMock()
        with patch.dict("sys.modules", {"anthropic": fake_sdk}):
            AnthropicProvider(api_key="k", timeout=123.0)

        kwargs = fake_sdk.Anthropic.call_args.kwargs
        assert kwargs["timeout"] == 123.0
        assert kwargs["max_retries"] == 0, "SDK retries multiply against ours"

    def test_falls_back_to_configured_timeout(self):
        from services.llm.providers.anthropic_provider import AnthropicProvider

        fake_sdk = MagicMock()
        with patch.dict("sys.modules", {"anthropic": fake_sdk}), patch(
            "services.llm.providers.openai_provider._config_timeout",
            return_value=900.0,
        ):
            AnthropicProvider(api_key="k")

        assert fake_sdk.Anthropic.call_args.kwargs["timeout"] == 900.0


class TestGeminiProviderTimeout:
    def test_timeout_is_passed_as_milliseconds(self):
        from services.llm.providers.gemini_provider import GeminiProvider

        fake_genai = MagicMock()
        fake_google = MagicMock(genai=fake_genai)
        with patch.dict(
            "sys.modules", {"google": fake_google, "google.genai": fake_genai}
        ):
            GeminiProvider(api_key="k", timeout=60.0)

        kwargs = fake_genai.Client.call_args.kwargs
        assert kwargs["http_options"] == {"timeout": 60_000}

    def test_falls_back_to_configured_timeout(self):
        from services.llm.providers.gemini_provider import GeminiProvider

        fake_genai = MagicMock()
        fake_google = MagicMock(genai=fake_genai)
        with patch.dict(
            "sys.modules", {"google": fake_google, "google.genai": fake_genai}
        ), patch(
            "services.llm.providers.openai_provider._config_timeout",
            return_value=900.0,
        ):
            GeminiProvider(api_key="k")

        assert fake_genai.Client.call_args.kwargs["http_options"] == {
            "timeout": 900_000
        }


class TestThresholdsAgreeWithRequestTimeout:
    def test_latency_ceiling_exceeds_the_request_timeout(self):
        """Otherwise the chain evicts the models the timeout exists to serve."""
        llm = LLMConfig()
        assert llm.fallback_max_latency_ms >= llm.request_timeout * 1000

    def test_first_chunk_timeout_allows_slow_reasoning_models(self):
        """180s killed the >3-minute time-to-first-token case."""
        assert PipelineConfig().stream_first_chunk_timeout >= 300

    def test_chunk_timeout_stays_short(self):
        """Once tokens flow, a long gap is a genuine stall — keep this tight."""
        assert PipelineConfig().stream_chunk_timeout <= 60
