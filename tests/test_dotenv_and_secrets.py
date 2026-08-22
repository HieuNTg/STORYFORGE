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
            with patch("dotenv.load_dotenv") as mock_load:
                config._load_dotenv_once()
        mock_load.assert_not_called()

    def test_loader_reads_dotenv_when_not_skipped(self):
        import config

        env = {k: v for k, v in os.environ.items() if k != "STORYFORGE_SKIP_DOTENV"}
        with patch.dict(os.environ, env, clear=True):
            with patch("dotenv.load_dotenv") as mock_load:
                config._load_dotenv_once()
        mock_load.assert_called_once()

    def test_env_overrides_reach_the_dataclasses(self):
        """Pins the payoff: _ENV_MAP only works once .env is loaded."""
        llm, pipeline = LLMConfig(), PipelineConfig()
        with patch.dict(os.environ, {"STORYFORGE_MODEL": "test-model-xyz"}):
            _apply_env_overrides(llm, pipeline)
        assert llm.model == "test-model-xyz"


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
