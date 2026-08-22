"""Regression tests: .env must reach the process, and secrets must not sit in the clear.

Nothing in the backend called load_dotenv, so STORYFORGE_SECRET_KEY was never
set. secret_manager therefore had no key, encryption at rest silently did
nothing, and data/config.json held API keys as plaintext. The same gap made all
30 entries of persistence._ENV_MAP dead, along with STORYFORGE_ALLOWED_ORIGINS,
REDIS_URL and DATABASE_URL.
"""

import json
import os
from unittest.mock import patch

from config.persistence import _apply_env_overrides
from config.defaults import LLMConfig, PipelineConfig
from services.secret_manager import (
    STORYFORGE_SECRET_KEY_ENV,
    has_plaintext_secrets,
    migrate_plaintext_secrets,
)


class TestDotenvWiring:
    def test_config_package_exposes_the_loader(self):
        import config

        assert hasattr(config, "_load_dotenv_once")

    def test_loader_is_a_noop_when_skipped(self):
        """The test suite relies on this guard to stay hermetic."""
        import config

        with patch.dict(os.environ, {"STORYFORGE_SKIP_DOTENV": "1"}):
            with patch("dotenv.dotenv_values") as mock_read:
                config._load_dotenv_once()
        mock_read.assert_not_called()

    def test_loader_reads_dotenv_when_not_skipped(self):
        import config

        env = {k: v for k, v in os.environ.items() if k != "STORYFORGE_SKIP_DOTENV"}
        with patch.dict(os.environ, env, clear=True):
            with patch("dotenv.dotenv_values", return_value={}) as mock_read:
                config._load_dotenv_once()
        mock_read.assert_called_once()

    def test_env_overrides_reach_the_dataclasses(self):
        """Pins the payoff: _ENV_MAP only works once .env is loaded."""
        llm, pipeline = LLMConfig(), PipelineConfig()
        with patch.dict(os.environ, {"STORYFORGE_MODEL": "test-model-xyz"}):
            _apply_env_overrides(llm, pipeline)
        assert llm.model == "test-model-xyz"


class TestDotenvDoesNotExportBlanks:
    """Found by booting the server during the Sprint 1 test plan.

    `.env` carries a dozen empty lines like `WEB_CONCURRENCY=`. load_dotenv
    exports those as empty strings, which is not the same as unset: uvicorn does
    `int(os.environ["WEB_CONCURRENCY"])` and crashed the server on startup, and
    every `os.environ.get(k, default)` elsewhere silently returns "" instead of
    its default.
    """

    def test_blank_values_are_skipped(self, monkeypatch):
        import config

        monkeypatch.delenv("STORYFORGE_SKIP_DOTENV", raising=False)
        monkeypatch.delenv("SF_BLANK_TEST", raising=False)
        monkeypatch.delenv("SF_SET_TEST", raising=False)
        with patch(
            "dotenv.dotenv_values",
            return_value={"SF_BLANK_TEST": "", "SF_SET_TEST": "value"},
        ):
            config._load_dotenv_once()

        assert "SF_BLANK_TEST" not in os.environ
        assert os.environ.get("SF_SET_TEST") == "value"

    def test_none_values_are_skipped(self, monkeypatch):
        import config

        monkeypatch.delenv("STORYFORGE_SKIP_DOTENV", raising=False)
        monkeypatch.delenv("SF_NONE_TEST", raising=False)
        with patch("dotenv.dotenv_values", return_value={"SF_NONE_TEST": None}):
            config._load_dotenv_once()

        assert "SF_NONE_TEST" not in os.environ

    def test_an_exported_variable_beats_the_file(self, monkeypatch):
        import config

        monkeypatch.delenv("STORYFORGE_SKIP_DOTENV", raising=False)
        monkeypatch.setenv("SF_PRECEDENCE_TEST", "from-shell")
        with patch(
            "dotenv.dotenv_values", return_value={"SF_PRECEDENCE_TEST": "from-file"}
        ):
            config._load_dotenv_once()

        assert os.environ["SF_PRECEDENCE_TEST"] == "from-shell"


class TestPlaceholderKeysAreRefused:
    """Also found live: the repo's .env ships STORYFORGE_SECRET_KEY set to
    `change-me-in-production`. Encrypting with it is worse than plaintext — the
    key is public, but the ENC: prefix makes the values look protected.
    """

    def test_the_shipped_placeholder_is_recognised(self):
        from services.secret_manager import is_placeholder_key

        assert is_placeholder_key("change-me-in-production") is True
        assert is_placeholder_key("CHANGE-ME-IN-PRODUCTION") is True
        assert is_placeholder_key("  changeme  ") is True

    def test_a_real_key_is_not_flagged(self):
        from services.secret_manager import is_placeholder_key

        assert is_placeholder_key("k7Fq2-real-random-9xZ") is False

    def test_encryption_is_refused_with_a_placeholder(self):
        from services.secret_manager import encrypt_value

        with patch.dict(
            os.environ, {STORYFORGE_SECRET_KEY_ENV: "change-me-in-production"}
        ):
            assert encrypt_value("sk-real-key") == "sk-real-key"

    def test_migration_is_refused_with_a_placeholder(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"llm": {"api_key": "sk-plain"}}), encoding="utf-8")

        with patch.dict(
            os.environ, {STORYFORGE_SECRET_KEY_ENV: "change-me-in-production"}
        ):
            assert migrate_plaintext_secrets(str(path)) is False

        assert json.loads(path.read_text(encoding="utf-8"))["llm"]["api_key"] == (
            "sk-plain"
        ), "a publicly known key must not be used to fake encryption"

    def test_a_real_key_still_encrypts(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"llm": {"api_key": "sk-plain"}}), encoding="utf-8")

        with patch.dict(os.environ, {STORYFORGE_SECRET_KEY_ENV: "k7Fq2-real-random"}):
            assert migrate_plaintext_secrets(str(path)) is True

        assert json.loads(path.read_text(encoding="utf-8"))["llm"]["api_key"].startswith(
            "ENC:"
        )


class TestPlaintextSecretDetection:
    def test_detects_a_plaintext_api_key(self):
        assert has_plaintext_secrets({"llm": {"api_key": "sk-plain-value"}}) is True

    def test_encrypted_values_are_not_flagged(self):
        assert has_plaintext_secrets({"llm": {"api_key": "ENC:abc123"}}) is False

    def test_empty_and_non_secret_fields_are_not_flagged(self):
        data = {"llm": {"api_key": "", "model": "gpt-4o", "temperature": 0.8}}
        assert has_plaintext_secrets(data) is False

    def test_nested_lists_are_inspected(self):
        assert has_plaintext_secrets({"llm": {"api_keys": ["sk-raw"]}}) is True


class TestSecretMigration:
    def _write(self, tmp_path, data):
        path = tmp_path / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_no_key_means_no_migration(self, tmp_path):
        path = self._write(tmp_path, {"llm": {"api_key": "sk-plain"}})
        env = {k: v for k, v in os.environ.items() if k != STORYFORGE_SECRET_KEY_ENV}
        with patch.dict(os.environ, env, clear=True):
            assert migrate_plaintext_secrets(path) is False
        assert json.loads(open(path, encoding="utf-8").read())["llm"]["api_key"] == (
            "sk-plain"
        )

    def test_plaintext_is_encrypted_in_place(self, tmp_path):
        path = self._write(tmp_path, {"llm": {"api_key": "sk-plain", "model": "m"}})
        with patch.dict(os.environ, {STORYFORGE_SECRET_KEY_ENV: "unit-test-key"}):
            assert migrate_plaintext_secrets(path) is True
            written = json.loads(open(path, encoding="utf-8").read())

        assert written["llm"]["api_key"].startswith("ENC:")
        assert written["llm"]["model"] == "m", "non-secret fields must be untouched"

    def test_migration_is_idempotent(self, tmp_path):
        path = self._write(tmp_path, {"llm": {"api_key": "sk-plain"}})
        with patch.dict(os.environ, {STORYFORGE_SECRET_KEY_ENV: "unit-test-key"}):
            assert migrate_plaintext_secrets(path) is True
            assert migrate_plaintext_secrets(path) is False

    def test_missing_file_is_not_an_error(self, tmp_path):
        with patch.dict(os.environ, {STORYFORGE_SECRET_KEY_ENV: "unit-test-key"}):
            assert migrate_plaintext_secrets(str(tmp_path / "absent.json")) is False


class TestSyncDriverUrlDoesNotAbortStartup:
    def test_sync_sqlite_url_degrades_instead_of_raising(self):
        """The repo's own .env ships sqlite:///./data/storyforge.db — a sync URL."""
        import services.infra.database as db

        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///./data/test.db"}):
            db._engine = None
            db._session_factory = None
            engine = db.get_engine()  # must not raise
        assert engine is None
