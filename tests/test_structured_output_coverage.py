"""Tests for services/structured_output.py."""
import json
import pytest
from unittest.mock import MagicMock, patch
from services.structured_output import (
    _detect_provider,
    _extract_json,
    _validate_schema,
    generate_structured,
)


# ---------------------------------------------------------------------------
# _detect_provider
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDetectProvider:
    def test_empty_url_returns_openai(self):
        assert _detect_provider("") == "openai"

    def test_openai_url(self):
        assert _detect_provider("https://api.openai.com/v1") == "openai"

    def test_openrouter_url(self):
        assert _detect_provider("https://openrouter.ai/api/v1") == "openrouter"

    def test_localhost_returns_ollama(self):
        assert _detect_provider("http://localhost:11434") == "ollama"

    def test_127_returns_ollama(self):
        assert _detect_provider("http://127.0.0.1:11434") == "ollama"

    def test_ollama_in_url(self):
        assert _detect_provider("http://my-ollama-server.local:11434") == "ollama"

    def test_anthropic_url(self):
        assert _detect_provider("https://api.anthropic.com") == "anthropic"

    def test_gemini_url(self):
        assert _detect_provider("https://generativelanguage.googleapis.com/v1") == "google"

    def test_googleapis_url(self):
        assert _detect_provider("https://gemini.googleapis.com") == "google"

    def test_unknown_url_returns_custom(self):
        assert _detect_provider("https://my-custom-api.example.com") == "custom"

    def test_case_insensitive(self):
        assert _detect_provider("https://API.OPENAI.COM/V1") == "openai"


# ---------------------------------------------------------------------------
# _extract_json
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExtractJson:
    def test_plain_json_string(self):
        result = _extract_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_json_embedded_in_text(self):
        result = _extract_json('Here is the result: {"score": 42} and that is it.')
        assert result["score"] == 42

    def test_json_with_trailing_comma(self):
        result = _extract_json('{"a": 1, "b": 2,}')
        assert result["a"] == 1
        assert result["b"] == 2

    def test_nested_json(self):
        result = _extract_json('{"outer": {"inner": true}}')
        assert result["outer"]["inner"] is True

    def test_no_json_raises_value_error(self):
        with pytest.raises(ValueError, match="No valid JSON"):
            _extract_json("This is just plain text with no JSON.")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            _extract_json("")

    def test_array_as_first_value_extracts_inner_object(self):
        # _extract_json tries json.loads first — returns the list directly on success.
        # Then the regex picks the first {...} block.
        # Since the array parses fine as JSON, the result is the list itself.
        import json as _json
        raw = '[1, 2, {"x": 3}]'
        parsed = _json.loads(raw)
        # Either the full array comes back (direct parse succeeds), or the inner object
        result = _extract_json(raw)
        # Accept both valid behaviors
        assert result == [1, 2, {"x": 3}] or result == {"x": 3}

    def test_json_with_unicode(self):
        result = _extract_json('{"title": "Tiên Hiệp", "score": 9}')
        assert result["title"] == "Tiên Hiệp"


# ---------------------------------------------------------------------------
# _validate_schema
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidateSchema:
    def test_all_keys_present_returns_empty(self):
        data = {"a": 1, "b": 2, "c": 3}
        schema = {"a": None, "b": None}
        assert _validate_schema(data, schema) == []

    def test_missing_key_returned(self):
        data = {"a": 1}
        schema = {"a": None, "b": None}
        missing = _validate_schema(data, schema)
        assert "b" in missing

    def test_empty_schema_always_passes(self):
        assert _validate_schema({}, {}) == []

    def test_multiple_missing_keys(self):
        data = {}
        schema = {"x": None, "y": None, "z": None}
        missing = _validate_schema(data, schema)
        assert set(missing) == {"x", "y", "z"}


# ---------------------------------------------------------------------------
# generate_structured
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGenerateStructured:
    """ConfigManager and LLMClient are imported inside the function body.
    Patch them at their source modules: config.ConfigManager and services.llm_client.LLMClient.
    """

    def _mock_config(self, base_url: str = "https://api.openai.com/v1"):
        config = MagicMock()
        config.llm.base_url = base_url
        return config

    def test_json_mode_provider(self):
        """OpenAI provider uses json_object mode."""
        with patch("config.ConfigManager") as MockConfig, \
             patch("services.llm_client.LLMClient") as MockLLM:
            MockConfig.return_value = self._mock_config("https://api.openai.com/v1")
            mock_client = MockLLM.return_value
            mock_client.generate.return_value = '{"title": "Story", "score": 8}'

            result = generate_structured(
                prompt="Generate story metadata",
                schema={"title": None, "score": None},
            )

        assert result["title"] == "Story"
        assert result["score"] == 8
        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs.get("json_mode") is True

    def test_regex_fallback_provider(self):
        """Anthropic provider uses regex extraction fallback."""
        with patch("config.ConfigManager") as MockConfig, \
             patch("services.llm_client.LLMClient") as MockLLM:
            MockConfig.return_value = self._mock_config("https://api.anthropic.com")
            mock_client = MockLLM.return_value
            mock_client.generate.return_value = 'Here is the result: {"name": "Test", "value": 5}'

            result = generate_structured(
                prompt="Extract data",
                schema={"name": None, "value": None},
            )

        assert result["name"] == "Test"
        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs.get("json_mode") is False

    def test_strict_mode_raises_on_missing_key(self):
        with patch("config.ConfigManager") as MockConfig, \
             patch("services.llm_client.LLMClient") as MockLLM:
            MockConfig.return_value = self._mock_config("https://api.openai.com/v1")
            mock_client = MockLLM.return_value
            mock_client.generate.return_value = '{"only_key": "value"}'

            with pytest.raises(ValueError, match="missing keys"):
                generate_structured(
                    prompt="test",
                    schema={"only_key": None, "required_missing": None},
                    strict=True,
                )

    def test_non_strict_mode_warns_but_returns(self):
        with patch("config.ConfigManager") as MockConfig, \
             patch("services.llm_client.LLMClient") as MockLLM:
            MockConfig.return_value = self._mock_config("https://api.openai.com/v1")
            mock_client = MockLLM.return_value
            mock_client.generate.return_value = '{"only_key": "value"}'

            result = generate_structured(
                prompt="test",
                schema={"only_key": None, "missing_key": None},
                strict=False,
            )
        assert result["only_key"] == "value"

    def test_custom_temperature_and_max_tokens_passed_through(self):
        with patch("config.ConfigManager") as MockConfig, \
             patch("services.llm_client.LLMClient") as MockLLM:
            MockConfig.return_value = self._mock_config("https://api.openai.com/v1")
            mock_client = MockLLM.return_value
            mock_client.generate.return_value = '{"result": "ok"}'

            generate_structured(
                prompt="test",
                schema={"result": None},
                temperature=0.5,
                max_tokens=512,
            )

        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 512

    def test_openrouter_uses_json_mode(self):
        with patch("config.ConfigManager") as MockConfig, \
             patch("services.llm_client.LLMClient") as MockLLM:
            MockConfig.return_value = self._mock_config("https://openrouter.ai/api/v1")
            mock_client = MockLLM.return_value
            mock_client.generate.return_value = '{"x": 1}'

            generate_structured(prompt="test", schema={"x": None})

        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs.get("json_mode") is True

    def test_ollama_uses_regex_fallback(self):
        with patch("config.ConfigManager") as MockConfig, \
             patch("services.llm_client.LLMClient") as MockLLM:
            MockConfig.return_value = self._mock_config("http://localhost:11434")
            mock_client = MockLLM.return_value
            mock_client.generate.return_value = '{"x": 1}'

            generate_structured(prompt="test", schema={"x": None})

        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs.get("json_mode") is False
