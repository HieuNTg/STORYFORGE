"""Auto-generated, persisted Fernet key for secrets at rest (Task 10)."""

import json

import pytest
from cryptography.fernet import Fernet

import services.secret_manager as sm
from services.secret_manager import decrypt_value, encrypt_value, ensure_secret_key


@pytest.fixture
def key_file(tmp_path, monkeypatch):
    path = tmp_path / ".secret_key"
    monkeypatch.delenv("STORYFORGE_SECRET_KEY", raising=False)
    monkeypatch.setattr(sm, "SECRET_KEY_FILE", path)
    return path


def test_generates_and_reuses_key(key_file):
    k1 = ensure_secret_key()
    k2 = ensure_secret_key()
    assert k1 == k2 and key_file.read_bytes().strip() == k1
    Fernet(k1)  # valid


def test_placeholder_env_ignored(key_file, monkeypatch):
    monkeypatch.setenv("STORYFORGE_SECRET_KEY", "change-me-in-production")
    assert ensure_secret_key() == key_file.read_bytes().strip()


def test_valid_env_key_used_directly(key_file, monkeypatch):
    env_key = Fernet.generate_key()
    monkeypatch.setenv("STORYFORGE_SECRET_KEY", env_key.decode())
    assert ensure_secret_key() == env_key
    assert not key_file.exists()


def test_invalid_env_key_exits(key_file, monkeypatch, capsys):
    monkeypatch.setenv("STORYFORGE_SECRET_KEY", "not-a-fernet-key")
    with pytest.raises(SystemExit) as exc:
        ensure_secret_key()
    assert exc.value.code == 2
    assert "Fernet.generate_key" in capsys.readouterr().err


@pytest.mark.parametrize("content", [b"", b"garbage"])
def test_corrupt_key_file_exits_without_regenerating(key_file, content):
    key_file.write_bytes(content)
    with pytest.raises(SystemExit) as exc:
        ensure_secret_key()
    assert exc.value.code == 2
    assert key_file.read_bytes() == content


def test_key_file_parent_created(tmp_path, monkeypatch):
    monkeypatch.delenv("STORYFORGE_SECRET_KEY", raising=False)
    path = tmp_path / "nested" / "dir" / ".secret_key"
    monkeypatch.setattr(sm, "SECRET_KEY_FILE", path)
    assert ensure_secret_key() == path.read_bytes().strip()


def test_roundtrip_encrypts(key_file):
    enc = encrypt_value("sk-abc")
    assert enc.startswith("ENC:") and "sk-abc" not in enc
    assert decrypt_value(enc) == "sk-abc"


def test_get_fernet_never_none(key_file):
    assert sm._get_fernet() is not None


def test_wrong_key_warns_once(key_file, monkeypatch, caplog):
    other = Fernet(Fernet.generate_key()).encrypt(b"x").decode()
    monkeypatch.setattr(sm, "_decrypt_warned", False)
    with caplog.at_level("WARNING", logger=sm.logger.name):
        assert decrypt_value("ENC:" + other) == ""
        assert decrypt_value("ENC:" + other) == ""
    assert len([r for r in caplog.records if "decrypt" in r.message.lower()]) == 1


def test_undecryptable_value_becomes_empty_and_app_starts(key_file, tmp_path, monkeypatch):
    import config.persistence as p
    from config.defaults import LLMConfig, PipelineConfig

    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"llm": {"api_key": "ENC:garbage"}}), encoding="utf-8")
    monkeypatch.setattr(p, "CONFIG_FILE", str(cfg))
    monkeypatch.setattr(p, "_SECRETS_FILE", str(tmp_path / "secrets.json"))
    monkeypatch.delenv("STORYFORGE_API_KEY", raising=False)
    llm, pipeline = LLMConfig(), PipelineConfig()
    p.load_config(llm, pipeline)
    assert llm.api_key == ""


def test_publish_never_overwrites_and_both_callers_get_disk_key(key_file):
    k1, k2 = Fernet.generate_key(), Fernet.generate_key()
    assert sm._publish_key(key_file, k1) is True
    assert sm._publish_key(key_file, k2) is False
    assert key_file.read_bytes().strip() == k1
    assert [p.name for p in key_file.parent.iterdir()] == [".secret_key"]


def test_publish_falls_back_to_excl_create_without_hardlinks(key_file, monkeypatch):
    def no_link(*a, **k):
        raise OSError("links unsupported")

    monkeypatch.setattr(sm.os, "link", no_link)
    k1, k2 = Fernet.generate_key(), Fernet.generate_key()
    assert sm._publish_key(key_file, k1) is True
    assert sm._publish_key(key_file, k2) is False
    assert key_file.read_bytes().strip() == k1


def test_race_loser_returns_winners_key(key_file, monkeypatch):
    winner = Fernet.generate_key()
    real = sm._publish_key

    def racing(path, key):
        real(path, winner)  # another process publishes first
        return real(path, key)

    monkeypatch.setattr(sm, "_publish_key", racing)
    assert ensure_secret_key() == winner
