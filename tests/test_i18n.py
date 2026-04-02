"""Tests for services/i18n.py — I18n singleton, t(), set_language(), fallback chain."""
from unittest.mock import patch, mock_open
import json
import threading
from services.i18n import I18n, SUPPORTED_LANGUAGES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_singleton():
    """Reset the I18n singleton between tests."""
    I18n._instance = None


VI_STRINGS = {
    "app.title": "StoryForge",
    "greeting": "Xin chào, {name}!",
    "only_vi": "Chỉ có trong tiếng Việt",
}

EN_STRINGS = {
    "app.title": "StoryForge",
    "greeting": "Hello, {name}!",
}


def _make_i18n_with_mocked_locales(vi_data=None, en_data=None):
    """Return a fresh I18n instance with mocked locale files."""
    _reset_singleton()
    json.dumps(vi_data or VI_STRINGS)
    json.dumps(en_data or EN_STRINGS)

    def _fake_read_locale(self, lang):
        if lang == "vi":
            return vi_data or VI_STRINGS
        if lang == "en":
            return en_data or EN_STRINGS
        return {}

    with patch.object(I18n, "_read_locale", _fake_read_locale):
        i18n = I18n()
    return i18n


# ---------------------------------------------------------------------------
# Singleton behaviour
# ---------------------------------------------------------------------------

class TestI18nSingleton:
    def test_same_instance_returned(self):
        _reset_singleton()
        a = I18n()
        b = I18n()
        assert a is b

    def test_instance_initialized_once(self):
        _reset_singleton()
        with patch.object(I18n, "_load_fallback") as mock_fallback:
            mock_fallback.side_effect = lambda: setattr(
                I18n._instance or I18n(), "_fallback", {}
            )
            I18n()
            call_count = mock_fallback.call_count
            _i2 = I18n()
            # _load_fallback should not be called again on second instantiation
            assert mock_fallback.call_count == call_count


# ---------------------------------------------------------------------------
# t() — translation and interpolation
# ---------------------------------------------------------------------------

class TestTranslate:
    def test_known_key_returns_string(self):
        i18n = _make_i18n_with_mocked_locales()
        result = i18n.t("app.title")
        assert result == "StoryForge"

    def test_unknown_key_returns_key_itself(self):
        i18n = _make_i18n_with_mocked_locales()
        result = i18n.t("nonexistent.key")
        assert result == "nonexistent.key"

    def test_interpolation_works(self):
        i18n = _make_i18n_with_mocked_locales()
        result = i18n.t("greeting", name="Alice")
        assert result == "Xin chào, Alice!"

    def test_interpolation_missing_variable_returns_raw_text(self):
        i18n = _make_i18n_with_mocked_locales()
        # Missing keyword arg — should not raise, returns unformatted text
        result = i18n.t("greeting")
        assert "{name}" in result or "Xin chào" in result

    def test_empty_string_key_returns_empty_string_or_key(self):
        i18n = _make_i18n_with_mocked_locales()
        result = i18n.t("")
        assert result == ""  # empty key → fallback returns ""

    def test_fallback_to_vi_when_en_missing_key(self):
        """Key in vi but not in en → falls back to vi string."""
        _reset_singleton()

        def _fake_read_locale(self, lang):
            if lang == "vi":
                return {"only_vi": "Solo in VI", "app.title": "SF"}
            return {"app.title": "SF"}  # en has no "only_vi"

        with patch.object(I18n, "_read_locale", _fake_read_locale):
            i18n = I18n()
            i18n.set_language("en")

        result = i18n.t("only_vi")
        assert result == "Solo in VI"

    def test_no_kwargs_returns_plain_string(self):
        i18n = _make_i18n_with_mocked_locales()
        result = i18n.t("app.title")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# set_language()
# ---------------------------------------------------------------------------

class TestSetLanguage:
    def test_set_to_en_switches_language(self):
        _reset_singleton()

        def _fake_read_locale(self, lang):
            if lang == "vi":
                return {"greeting": "Xin chào, {name}!"}
            if lang == "en":
                return {"greeting": "Hello, {name}!"}
            return {}

        with patch.object(I18n, "_read_locale", _fake_read_locale):
            i18n = I18n()
            i18n.set_language("en")

        assert i18n.lang == "en"
        result = i18n.t("greeting", name="Bob")
        assert result == "Hello, Bob!"

    def test_set_to_vi_restores_vietnamese(self):
        _reset_singleton()

        def _fake_read_locale(self, lang):
            if lang == "vi":
                return {"greeting": "Xin chào, {name}!"}
            return {"greeting": "Hello, {name}!"}

        with patch.object(I18n, "_read_locale", _fake_read_locale):
            i18n = I18n()
            i18n.set_language("en")
            i18n.set_language("vi")

        assert i18n.lang == "vi"
        result = i18n.t("greeting", name="Alice")
        assert "Xin chào" in result

    def test_unsupported_language_ignored(self):
        i18n = _make_i18n_with_mocked_locales()
        original_lang = i18n.lang
        i18n.set_language("jp")  # not in SUPPORTED_LANGUAGES
        assert i18n.lang == original_lang

    def test_lang_property_reflects_current_language(self):
        _reset_singleton()

        def _fake_read_locale(self, lang):
            return {}

        with patch.object(I18n, "_read_locale", _fake_read_locale):
            i18n = I18n()
        assert i18n.lang == "vi"


# ---------------------------------------------------------------------------
# available_languages()
# ---------------------------------------------------------------------------

class TestAvailableLanguages:
    def test_returns_dict(self):
        langs = I18n.available_languages()
        assert isinstance(langs, dict)

    def test_contains_vi_and_en(self):
        langs = I18n.available_languages()
        assert "vi" in langs
        assert "en" in langs

    def test_matches_supported_languages(self):
        langs = I18n.available_languages()
        assert set(langs.keys()) == set(SUPPORTED_LANGUAGES.keys())

    def test_returns_copy_not_original(self):
        langs = I18n.available_languages()
        langs["xx"] = "Test"
        assert "xx" not in I18n.available_languages()


# ---------------------------------------------------------------------------
# _read_locale() — file loading
# ---------------------------------------------------------------------------

class TestReadLocale:
    def test_missing_file_returns_empty_dict(self):
        _reset_singleton()
        with patch("os.path.exists", return_value=False):
            i18n = I18n.__new__(I18n)
            i18n._initialized = False
            result = i18n._read_locale("xx")
        assert result == {}

    def test_malformed_json_returns_empty_dict(self):
        _reset_singleton()
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="not valid json {{")):
            i18n = I18n.__new__(I18n)
            i18n._initialized = False
            result = i18n._read_locale("vi")
        assert result == {}

    def test_valid_json_returns_parsed_dict(self):
        _reset_singleton()
        data = {"key": "value"}
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(data))):
            i18n = I18n.__new__(I18n)
            i18n._initialized = False
            result = i18n._read_locale("vi")
        assert result == data


# ---------------------------------------------------------------------------
# Thread safety (basic smoke test)
# ---------------------------------------------------------------------------

class TestThreadSafety:
    def test_concurrent_instantiation_returns_same_instance(self):
        _reset_singleton()
        instances = []

        def _get_instance():
            with patch.object(I18n, "_read_locale", lambda self, lang: {}):
                instances.append(I18n())

        threads = [threading.Thread(target=_get_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(i is instances[0] for i in instances)
