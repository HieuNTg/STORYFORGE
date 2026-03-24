"""Tests for services/llm_client.py — fallback chain, retry, transient errors."""

import unittest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Tests: _is_transient helper
# ---------------------------------------------------------------------------

class TestIsTransient(unittest.TestCase):

    def test_429_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("rate limit 429 exceeded")
        self.assertTrue(_is_transient(exc))

    def test_500_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("internal server error 500")
        self.assertTrue(_is_transient(exc))

    def test_502_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("bad gateway 502")
        self.assertTrue(_is_transient(exc))

    def test_503_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("service unavailable 503")
        self.assertTrue(_is_transient(exc))

    def test_504_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("gateway timeout 504")
        self.assertTrue(_is_transient(exc))

    def test_timeout_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("request timeout")
        self.assertTrue(_is_transient(exc))

    def test_connection_error_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("connection refused")
        self.assertTrue(_is_transient(exc))

    def test_reset_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("connection reset by peer")
        self.assertTrue(_is_transient(exc))

    def test_broken_pipe_is_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("broken pipe")
        self.assertTrue(_is_transient(exc))

    def test_401_not_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("unauthorized 401 invalid api key")
        self.assertFalse(_is_transient(exc))

    def test_404_not_transient(self):
        from services.llm_client import _is_transient
        exc = Exception("not found 404")
        self.assertFalse(_is_transient(exc))

    def test_generic_error_not_transient(self):
        from services.llm_client import _is_transient
        exc = ValueError("bad value")
        self.assertFalse(_is_transient(exc))


# ---------------------------------------------------------------------------
# Helpers to build config mocks
# ---------------------------------------------------------------------------

def _make_llm_config(
    api_key="key",
    base_url="http://api.test",
    model="gpt-4",
    cheap_model="",
    cheap_base_url="",
    fallback_models=None,
    temperature=0.7,
    max_tokens=2000,
    cache_enabled=False,
    cache_ttl_days=7,
    backend_type="api",
    language="vi",
):
    cfg = MagicMock()
    cfg.llm.api_key = api_key
    cfg.llm.base_url = base_url
    cfg.llm.model = model
    cfg.llm.cheap_model = cheap_model
    cfg.llm.cheap_base_url = cheap_base_url
    cfg.llm.fallback_models = fallback_models or []
    cfg.llm.temperature = temperature
    cfg.llm.max_tokens = max_tokens
    cfg.llm.cache_enabled = cache_enabled
    cfg.llm.cache_ttl_days = cache_ttl_days
    cfg.llm.backend_type = backend_type
    cfg.pipeline.language = language
    cfg.pipeline.share_base_url = ""
    return cfg


def _reset_llm_singleton():
    """Reset LLMClient singleton between tests."""
    from services import llm_client
    llm_client.LLMClient._instance = None


# ---------------------------------------------------------------------------
# Tests: _build_fallback_chain
# ---------------------------------------------------------------------------

class TestBuildFallbackChain(unittest.TestCase):

    def setUp(self):
        _reset_llm_singleton()

    def tearDown(self):
        _reset_llm_singleton()

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.OpenAI")
    def test_default_tier_starts_with_primary(self, MockOpenAI, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        config = _make_llm_config()
        # Manually set _current_model
        client._current_model = "gpt-4"
        mock_openai = MagicMock()
        client._client = mock_openai
        client._last_key = "http://api.test:key"
        chain = client._build_fallback_chain(config, "default")
        self.assertTrue(len(chain) >= 1)
        self.assertEqual(chain[0]["label"], "primary")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.OpenAI")
    def test_cheap_tier_uses_cheap_model(self, MockOpenAI, MockCM):
        from services.llm_client import LLMClient
        cfg = _make_llm_config(cheap_model="gpt-3.5-turbo", cheap_base_url="http://cheap.test")
        MockCM.return_value = cfg
        client = LLMClient()
        client._current_model = "gpt-4"
        client._client = MagicMock()
        client._last_key = "http://api.test:key"
        MockOpenAI.return_value = MagicMock()
        chain = client._build_fallback_chain(cfg, "cheap")
        self.assertTrue(any("cheap" in p["label"] for p in chain))
        self.assertEqual(chain[0]["model"], "gpt-3.5-turbo")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.OpenAI")
    def test_fallback_models_added_to_chain(self, MockOpenAI, MockCM):
        from services.llm_client import LLMClient
        fallbacks = [{"model": "claude-3", "base_url": "http://claude.test", "api_key": "ckey"}]
        cfg = _make_llm_config(fallback_models=fallbacks)
        MockCM.return_value = cfg
        client = LLMClient()
        client._current_model = "gpt-4"
        client._client = MagicMock()
        client._last_key = "http://api.test:key"
        MockOpenAI.return_value = MagicMock()
        chain = client._build_fallback_chain(cfg, "default")
        labels = [p["label"] for p in chain]
        self.assertTrue(any("fallback:claude-3" in lbl for lbl in labels))

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.OpenAI")
    def test_no_cheap_model_skips_cheap_entry(self, MockOpenAI, MockCM):
        from services.llm_client import LLMClient
        cfg = _make_llm_config(cheap_model="")
        MockCM.return_value = cfg
        client = LLMClient()
        client._current_model = "gpt-4"
        client._client = MagicMock()
        client._last_key = "http://api.test:key"
        chain = client._build_fallback_chain(cfg, "default")
        labels = [p["label"] for p in chain]
        self.assertFalse(any("cheap" in lbl for lbl in labels))

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.OpenAI")
    def test_fallback_without_model_skipped(self, MockOpenAI, MockCM):
        from services.llm_client import LLMClient
        fallbacks = [{"model": "", "base_url": "http://test.com", "api_key": "k"}]
        cfg = _make_llm_config(fallback_models=fallbacks)
        MockCM.return_value = cfg
        client = LLMClient()
        client._current_model = "gpt-4"
        client._client = MagicMock()
        client._last_key = "http://api.test:key"
        chain = client._build_fallback_chain(cfg, "default")
        labels = [p["label"] for p in chain]
        self.assertFalse(any("fallback:" in lbl and lbl.endswith(":") for lbl in labels))


# ---------------------------------------------------------------------------
# Tests: _try_provider
# ---------------------------------------------------------------------------

class TestTryProvider(unittest.TestCase):

    def setUp(self):
        _reset_llm_singleton()

    def tearDown(self):
        _reset_llm_singleton()

    @patch("services.llm_client.ConfigManager")
    def test_try_provider_success(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        mock_openai = MagicMock()
        response = MagicMock()
        response.choices[0].message.content = "Hello!"
        mock_openai.chat.completions.create.return_value = response

        provider = {"client": mock_openai, "model": "gpt-4", "label": "primary"}
        result = client._try_provider(provider, [{"role": "user", "content": "hi"}], 0.7, 1000, False)
        self.assertEqual(result, "Hello!")

    @patch("services.llm_client.ConfigManager")
    def test_try_provider_json_mode(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        mock_openai = MagicMock()
        response = MagicMock()
        response.choices[0].message.content = '{"key": "value"}'
        mock_openai.chat.completions.create.return_value = response

        provider = {"client": mock_openai, "model": "gpt-4", "label": "primary"}
        result = client._try_provider(provider, [], 0.5, 500, json_mode=True)
        call_kwargs = mock_openai.chat.completions.create.call_args[1]
        self.assertIn("response_format", call_kwargs)
        self.assertEqual(call_kwargs["response_format"]["type"], "json_object")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.time")
    def test_try_provider_retries_on_transient(self, mock_time, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        mock_openai = MagicMock()
        response = MagicMock()
        response.choices[0].message.content = "OK"
        # First call fails with transient, second succeeds
        mock_openai.chat.completions.create.side_effect = [
            Exception("timeout"),
            response,
        ]

        provider = {"client": mock_openai, "model": "gpt-4", "label": "primary"}
        result = client._try_provider(provider, [], 0.7, 1000, False)
        self.assertEqual(result, "OK")
        self.assertEqual(mock_openai.chat.completions.create.call_count, 2)

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.time")
    def test_try_provider_raises_after_max_attempts(self, mock_time, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        mock_openai = MagicMock()
        exc = Exception("timeout")
        mock_openai.chat.completions.create.side_effect = exc

        provider = {"client": mock_openai, "model": "gpt-4", "label": "primary"}
        with self.assertRaises(Exception):
            client._try_provider(provider, [], 0.7, 1000, False)

    @patch("services.llm_client.ConfigManager")
    def test_try_provider_empty_content_returns_empty_string(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        mock_openai = MagicMock()
        response = MagicMock()
        response.choices[0].message.content = None
        mock_openai.chat.completions.create.return_value = response

        provider = {"client": mock_openai, "model": "gpt-4", "label": "primary"}
        result = client._try_provider(provider, [], 0.7, 1000, False)
        self.assertEqual(result, "")


# ---------------------------------------------------------------------------
# Tests: generate — fallback chain behavior
# ---------------------------------------------------------------------------

class TestGenerateFallback(unittest.TestCase):

    def setUp(self):
        _reset_llm_singleton()

    def tearDown(self):
        _reset_llm_singleton()

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_uses_primary_on_success(self, MockCache, MockCM):
        from services.llm_client import LLMClient
        cfg = _make_llm_config()
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = None

        client = LLMClient()
        client._is_web_backend = MagicMock(return_value=False)
        primary = MagicMock()
        response = MagicMock()
        response.choices[0].message.content = "Primary result"
        primary.chat.completions.create.return_value = response
        client._build_fallback_chain = MagicMock(return_value=[
            {"client": primary, "model": "gpt-4", "label": "primary"}
        ])

        with patch("services.prompts.localize_prompt", side_effect=lambda p, l: p):
            result = client.generate("system", "user", temperature=0.5)
        self.assertEqual(result, "Primary result")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_falls_back_on_transient_error(self, MockCache, MockCM):
        from services.llm_client import LLMClient
        cfg = _make_llm_config()
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = None

        client = LLMClient()
        client._is_web_backend = MagicMock(return_value=False)
        primary = MagicMock()
        primary.chat.completions.create.side_effect = Exception("timeout")
        fallback = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = "Fallback result"
        fallback.chat.completions.create.return_value = resp
        client._build_fallback_chain = MagicMock(return_value=[
            {"client": primary, "model": "gpt-4", "label": "primary"},
            {"client": fallback, "model": "gpt-3.5", "label": "cheap:gpt-3.5"},
        ])

        with patch("services.prompts.localize_prompt", side_effect=lambda p, l: p):
            with patch("services.llm_client.time"):
                result = client.generate("system", "user")
        self.assertEqual(result, "Fallback result")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_raises_when_all_providers_fail(self, MockCache, MockCM):
        from services.llm_client import LLMClient
        cfg = _make_llm_config()
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = None

        client = LLMClient()
        client._is_web_backend = MagicMock(return_value=False)
        failing = MagicMock()
        failing.chat.completions.create.side_effect = Exception("timeout")
        client._build_fallback_chain = MagicMock(return_value=[
            {"client": failing, "model": "gpt-4", "label": "primary"},
        ])

        with patch("services.prompts.localize_prompt", side_effect=lambda p, l: p):
            with patch("services.llm_client.time"):
                with self.assertRaises(RuntimeError):
                    client.generate("system", "user")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_returns_cached_result(self, MockCache, MockCM):
        from services.llm_client import LLMClient
        cfg = _make_llm_config(cache_enabled=True)
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = "cached response"

        client = LLMClient()
        client._is_web_backend = MagicMock(return_value=False)

        with patch("services.prompts.localize_prompt", side_effect=lambda p, l: p):
            result = client.generate("system", "user", temperature=0.5)
        self.assertEqual(result, "cached response")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_stops_on_non_transient_error(self, MockCache, MockCM):
        from services.llm_client import LLMClient
        cfg = _make_llm_config()
        MockCM.return_value = cfg
        MockCache.return_value.get.return_value = None

        client = LLMClient()
        client._is_web_backend = MagicMock(return_value=False)
        primary = MagicMock()
        # 401 Unauthorized — not transient, should NOT try fallback
        primary.chat.completions.create.side_effect = Exception("401 unauthorized")
        fallback = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = "Fallback"
        fallback.chat.completions.create.return_value = resp
        client._build_fallback_chain = MagicMock(return_value=[
            {"client": primary, "model": "gpt-4", "label": "primary"},
            {"client": fallback, "model": "gpt-3.5", "label": "cheap"},
        ])

        with patch("services.prompts.localize_prompt", side_effect=lambda p, l: p):
            with self.assertRaises(Exception):
                client.generate("system", "user")
        # Fallback should NOT be tried for non-transient errors
        fallback.chat.completions.create.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _repair_json
# ---------------------------------------------------------------------------

class TestRepairJson(unittest.TestCase):

    def setUp(self):
        _reset_llm_singleton()

    def tearDown(self):
        _reset_llm_singleton()

    @patch("services.llm_client.ConfigManager")
    def test_removes_trailing_comma_in_object(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        result = LLMClient._repair_json('{"key": "value",}')
        self.assertNotIn(",}", result)

    @patch("services.llm_client.ConfigManager")
    def test_removes_trailing_comma_in_array(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        result = LLMClient._repair_json('[1, 2, 3,]')
        self.assertNotIn(",]", result)

    @patch("services.llm_client.ConfigManager")
    def test_extracts_json_from_surrounding_text(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        text = 'Here is some JSON: {"key": "value"} and more text'
        result = LLMClient._repair_json(text)
        self.assertTrue(result.startswith("{"))
        self.assertTrue(result.endswith("}"))

    @patch("services.llm_client.ConfigManager")
    def test_returns_text_unchanged_if_no_markers(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        text = "just plain text"
        result = LLMClient._repair_json(text)
        # No braces/brackets found, returns original
        self.assertEqual(result, text)


# ---------------------------------------------------------------------------
# Tests: generate_json
# ---------------------------------------------------------------------------

class TestGenerateJson(unittest.TestCase):

    def setUp(self):
        _reset_llm_singleton()

    def tearDown(self):
        _reset_llm_singleton()

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_json_parses_valid(self, MockCache, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        MockCache.return_value.get.return_value = None
        client = LLMClient()
        client.generate = MagicMock(return_value='{"result": "ok"}')
        result = client.generate_json("system", "user")
        self.assertEqual(result["result"], "ok")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_json_strips_markdown_code_block(self, MockCache, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        MockCache.return_value.get.return_value = None
        client = LLMClient()
        client.generate = MagicMock(return_value='```json\n{"key": "value"}\n```')
        result = client.generate_json("system", "user")
        self.assertEqual(result["key"], "value")

    @patch("services.llm_client.ConfigManager")
    @patch("services.llm_client.LLMCache")
    def test_generate_json_repairs_trailing_comma(self, MockCache, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        MockCache.return_value.get.return_value = None
        client = LLMClient()
        # Return value with trailing comma, repaired by _repair_json
        client.generate = MagicMock(return_value='{"key": "val",}')
        result = client.generate_json("system", "user")
        self.assertEqual(result["key"], "val")


# ---------------------------------------------------------------------------
# Tests: check_connection
# ---------------------------------------------------------------------------

class TestCheckConnection(unittest.TestCase):

    def setUp(self):
        _reset_llm_singleton()

    def tearDown(self):
        _reset_llm_singleton()

    @patch("services.llm_client.ConfigManager")
    def test_check_connection_success(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        client._is_web_backend = MagicMock(return_value=False)
        mock_openai = MagicMock()
        response = MagicMock()
        mock_openai.chat.completions.create.return_value = response
        client._get_client = MagicMock(return_value=mock_openai)
        client._current_model = "gpt-4"
        ok, msg = client.check_connection()
        self.assertTrue(ok)
        self.assertIn("thành công", msg)

    @patch("services.llm_client.ConfigManager")
    def test_check_connection_failure(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        client._is_web_backend = MagicMock(return_value=False)
        mock_openai = MagicMock()
        mock_openai.chat.completions.create.side_effect = Exception("connection refused")
        client._get_client = MagicMock(return_value=mock_openai)
        ok, msg = client.check_connection()
        self.assertFalse(ok)
        self.assertIn("Lỗi", msg)

    @patch("services.llm_client.ConfigManager")
    def test_check_connection_web_backend(self, MockCM):
        from services.llm_client import LLMClient
        MockCM.return_value = _make_llm_config()
        client = LLMClient()
        client._is_web_backend = MagicMock(return_value=True)
        web_client = MagicMock()
        web_client.check_connection.return_value = (True, "Web OK")
        client._get_web_client = MagicMock(return_value=web_client)
        ok, msg = client.check_connection()
        self.assertTrue(ok)
        self.assertEqual(msg, "Web OK")


if __name__ == "__main__":
    unittest.main()
