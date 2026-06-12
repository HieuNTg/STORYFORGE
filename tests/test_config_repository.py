"""Unit tests for the config repository trio (previously untested).

Covers services/_config_repo_json.py (against tmp_path files),
services/_config_repo_pg.py (Sprint 7 stub contract), and the
services/infra/config_repository.py factory (singleton + backend selection).
asyncio_mode = "auto" — async tests run directly.
"""

from __future__ import annotations

import json

import pytest

import services.infra.config_repository as factory_module
from services._config_repo_json import JsonFileConfigRepository
from services._config_repo_pg import PostgresConfigRepository
from services.infra.config_repository import get_config_repository


@pytest.fixture
def repo(tmp_path):
    return JsonFileConfigRepository(str(tmp_path / "config.json"))


class TestJsonFileRepository:
    async def test_set_then_get_roundtrip(self, repo):
        assert await repo.set_config("llm", {"model": "gpt-x"}) is True
        assert await repo.get_config("llm") == {"model": "gpt-x"}

    async def test_dotted_key_creates_nested_structure(self, repo, tmp_path):
        await repo.set_config("llm.fallback", {"model": "haiku"})
        assert await repo.get_config("llm.fallback") == {"model": "haiku"}
        on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert on_disk == {"llm": {"fallback": {"model": "haiku"}}}

    async def test_missing_key_returns_empty_dict(self, repo):
        assert await repo.get_config("không.tồn.tại") == {}

    async def test_non_dict_leaf_returns_empty_dict(self, repo, tmp_path):
        (tmp_path / "config.json").write_text(
            json.dumps({"llm": {"model": "chuỗi"}}), encoding="utf-8"
        )
        assert await repo.get_config("llm.model") == {}

    async def test_get_all_returns_full_document(self, repo):
        await repo.set_config("a", {"x": 1})
        await repo.set_config("b.c", {"y": 2})
        assert await repo.get_all() == {"a": {"x": 1}, "b": {"c": {"y": 2}}}

    async def test_delete_existing_key(self, repo):
        await repo.set_config("a.b", {"x": 1})
        assert await repo.delete_config("a.b") is True
        assert await repo.get_config("a.b") == {}
        # parent survives deletion of the leaf
        assert await repo.get_all() == {"a": {}}

    async def test_delete_missing_key_returns_false(self, repo):
        assert await repo.delete_config("không.có") is False

    async def test_corrupt_file_reads_as_empty(self, repo, tmp_path):
        (tmp_path / "config.json").write_text("{hỏng json", encoding="utf-8")
        assert await repo.get_all() == {}

    async def test_set_overwrites_without_clobbering_siblings(self, repo):
        await repo.set_config("llm.primary", {"model": "a"})
        await repo.set_config("llm.fallback", {"model": "b"})
        await repo.set_config("llm.primary", {"model": "c"})
        assert await repo.get_all() == {
            "llm": {"primary": {"model": "c"}, "fallback": {"model": "b"}}
        }

    async def test_write_is_valid_json_on_disk(self, repo, tmp_path):
        await repo.set_config("tiêu đề", {"truyện": "Tiên Hiệp"})
        on_disk = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
        assert on_disk["tiêu đề"] == {"truyện": "Tiên Hiệp"}


class TestPostgresStub:
    @pytest.mark.parametrize(
        "method,args",
        [
            ("get_config", ("k",)),
            ("set_config", ("k", {})),
            ("get_all", ()),
            ("delete_config", ("k",)),
        ],
    )
    async def test_every_operation_raises_not_implemented(self, method, args):
        stub = PostgresConfigRepository()
        with pytest.raises(NotImplementedError, match=method):
            await getattr(stub, method)(*args)


class TestFactory:
    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        saved = factory_module._instance
        factory_module._instance = None
        yield
        factory_module._instance = saved

    def test_defaults_to_json_backend(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        repo = get_config_repository(str(tmp_path / "config.json"))
        assert isinstance(repo, JsonFileConfigRepository)

    def test_database_url_selects_postgres_stub(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host/db")
        assert isinstance(get_config_repository(), PostgresConfigRepository)

    def test_factory_returns_singleton(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        first = get_config_repository(str(tmp_path / "config.json"))
        second = get_config_repository(str(tmp_path / "khác.json"))
        assert first is second
