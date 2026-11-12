"""Task 13: every run reads its own config snapshot.

Bugs pinned here:

* ``PUT /api/config`` mutated the ``ConfigManager`` singleton in place and a
  running pipeline re-read it mid-run, so a Settings save changed the model
  (or any flag) under a run that was already going.
* ``/api/pipeline/run`` applied per-run overrides to that same singleton, so
  two concurrent runs were last-writer-wins.
* The singleton was marked initialised *before* it finished loading, so a
  second thread could get an instance with no ``llm`` attribute yet.
"""

from __future__ import annotations

import asyncio
import contextvars
import threading
import time

import pytest

import config.config as config_module
from config import ConfigManager

from services.llm.run_context import run_in_thread


def _read_model_and_language() -> tuple[str, str]:
    cfg = ConfigManager()
    return cfg.llm.model, cfg.pipeline.language


# ─── snapshot / run_scope primitives ────────────────────────────────────────


class TestSnapshot:
    def test_snapshot_is_independent_of_the_singleton(self, monkeypatch):
        live = ConfigManager()
        monkeypatch.setattr(live.llm, "model", "m1")

        snap = live.snapshot()
        live.llm.model = "other"

        assert snap.llm.model == "m1"
        assert snap.llm is not live.llm
        assert snap.pipeline is not live.pipeline
        assert ConfigManager() is live, "a snapshot must not replace the singleton"

    def test_constructor_returns_the_active_snapshot_without_reloading(
        self, monkeypatch
    ):
        snap = ConfigManager().snapshot()

        def _boom(*_a, **_kw):
            raise AssertionError("ConfigManager() reloaded config inside run_scope")

        monkeypatch.setattr(config_module, "load_config", _boom)
        with config_module.run_scope(snap):
            assert ConfigManager() is snap
        assert ConfigManager() is not snap

    def test_run_scope_nests_and_restores(self):
        a = ConfigManager().snapshot()
        b = ConfigManager().snapshot()
        with config_module.run_scope(a):
            with config_module.run_scope(b):
                assert ConfigManager() is b
            assert ConfigManager() is a

    def test_snapshot_inside_a_scope_copies_the_scope(self):
        outer = ConfigManager().snapshot()
        outer.pipeline.language = "en"
        with config_module.run_scope(outer):
            inner = ConfigManager().snapshot()
        assert inner is not outer
        assert inner.pipeline.language == "en"


# ─── settings change mid-run ────────────────────────────────────────────────


async def test_settings_change_mid_run_does_not_affect_run(monkeypatch):
    from api.config_routes import ConfigUpdate, save_config

    monkeypatch.setattr(ConfigManager().llm, "model", "m1")
    monkeypatch.setattr(ConfigManager().llm, "api_key", "sk-task13-test")
    seen: list[str] = []
    started = asyncio.Event()
    resume = asyncio.Event()

    async def _stage():
        # fake pipeline stage inside run_scope; reads before and after the save
        seen.append(ConfigManager().llm.model)
        started.set()
        await resume.wait()
        # a thread hop must carry the snapshot along (Task 12 helpers)
        seen.append((await run_in_thread(_read_model_and_language))[0])

    with config_module.run_scope(ConfigManager().snapshot()):
        task = asyncio.create_task(_stage())

    await started.wait()
    save_config(ConfigUpdate(model="other"))  # the Settings page, mid-run
    assert ConfigManager().llm.model == "other"
    resume.set()
    await task

    assert seen == ["m1", "m1"]


async def test_orchestrator_run_ignores_settings_saved_mid_run(monkeypatch):
    """run_full_pipeline runs against the snapshot taken at construction."""
    import pipeline.orchestrator_layers as layers
    from api.config_routes import ConfigUpdate, save_config
    from pipeline.orchestrator import PipelineOrchestrator

    monkeypatch.setattr(ConfigManager().llm, "model", "m1")
    monkeypatch.setattr(ConfigManager().llm, "api_key", "sk-task13-test")
    orch = PipelineOrchestrator(session_id="task13-mid-run")
    seen: list[str] = []
    started = threading.Event()
    resume = threading.Event()

    async def _fake_body(self, **_kw):
        seen.append(ConfigManager().llm.model)
        seen.append(self.story_gen.config.llm.model)
        started.set()
        await asyncio.to_thread(resume.wait, 5)
        seen.append((await run_in_thread(_read_model_and_language))[0])
        return None

    monkeypatch.setattr(layers, "_run_full_pipeline_body", _fake_body)

    def _drive():
        contextvars.Context().run(
            asyncio.run, orch.run_full_pipeline(title="t", genre="g", idea="i")
        )

    worker = threading.Thread(target=_drive)
    worker.start()
    assert started.wait(5)
    save_config(ConfigUpdate(model="other"))
    resume.set()
    worker.join(10)

    assert seen == ["m1", "m1", "m1"]


# ─── per-run overrides isolated between concurrent runs ─────────────────────


def test_overrides_isolated_between_concurrent_runs(monkeypatch):
    import pipeline.orchestrator_layers as layers
    from api.pipeline_routes import _apply_run_overrides
    from pipeline.orchestrator import PipelineOrchestrator

    live = ConfigManager()
    monkeypatch.setattr(live.pipeline, "language", "vi")
    monkeypatch.setattr(live.pipeline, "enable_quality_gate", True)

    orch_a = PipelineOrchestrator(session_id="task13-a")
    orch_b = PipelineOrchestrator(session_id="task13-b")
    # same order as two /pipeline/run requests arriving back to back
    _apply_run_overrides(
        orch_a.config.pipeline, {"language": "en", "enable_quality_gate": False}
    )
    _apply_run_overrides(
        orch_b.config.pipeline, {"language": "vi", "enable_quality_gate": True}
    )

    seen: dict[str, list] = {"task13-a": [], "task13-b": []}
    barrier = threading.Barrier(2, timeout=5)

    async def _fake_body(self, **_kw):
        rec = seen[self.session_id]
        rec.append(ConfigManager().pipeline.language)
        rec.append(self.story_gen.config.pipeline.language)
        await asyncio.to_thread(barrier.wait)  # both runs are now in flight
        rec.append((await run_in_thread(_read_model_and_language))[1])
        rec.append(ConfigManager().pipeline.enable_quality_gate)
        return None

    monkeypatch.setattr(layers, "_run_full_pipeline_body", _fake_body)

    def _drive(orch):
        contextvars.Context().run(
            asyncio.run, orch.run_full_pipeline(title="t", genre="g", idea="i")
        )

    workers = [threading.Thread(target=_drive, args=(o,)) for o in (orch_a, orch_b)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(10)

    assert seen["task13-a"] == ["en", "en", "en", False]
    assert seen["task13-b"] == ["vi", "vi", "vi", True]
    # the overrides never touched the live settings
    assert live.pipeline.language == "vi"
    assert live.pipeline.enable_quality_gate is True


def test_restore_helper_is_gone():
    """Overrides live on the run's snapshot, so there is nothing to restore."""
    import api.pipeline_routes as routes

    assert not hasattr(routes, "_restore_run_overrides")


# ─── init race ──────────────────────────────────────────────────────────────


def test_singleton_not_visible_half_initialised(monkeypatch):
    real_load = config_module.load_config
    loading = threading.Event()

    def _slow_load(llm, pipeline):
        loading.set()
        time.sleep(0.3)
        real_load(llm, pipeline)
        llm.model = "loaded-model"

    monkeypatch.setattr(config_module, "load_config", _slow_load)
    monkeypatch.setattr(ConfigManager, "_instance", None)

    results: dict[str, object] = {}

    def _first():
        results["first"] = ConfigManager().llm.model

    def _second():
        try:
            results["second"] = ConfigManager().llm.model
        except Exception as exc:  # AttributeError on the half-built instance
            results["second"] = exc

    t1 = threading.Thread(target=_first)
    t1.start()
    assert loading.wait(5)
    t2 = threading.Thread(target=_second)
    t2.start()
    t1.join(5)
    t2.join(5)

    assert results["first"] == "loaded-model"
    assert results["second"] == "loaded-model"


@pytest.fixture(autouse=True)
def _keep_singleton(monkeypatch):
    """Tests here may reset the singleton; put the session's one back after."""
    original = ConfigManager._instance
    yield
    ConfigManager._instance = original


# ─── fix round 1: the LLM client reads the run's model / key ─────────────────


@pytest.fixture
def _llm_live(monkeypatch):
    """Live settings for an OpenAI-style primary, no per-layer overrides."""
    from services.llm import client as client_module
    from services.llm_client import LLMClient

    live = ConfigManager()
    for field, value in {
        "model": "gpt-4o",
        "api_key": "sk-task13-a",
        "base_url": "https://api.openai.com/v1",
        "api_keys": [],
        "fallback_models": [],
        "cheap_model": "",
        "layer1_model": "",
        "layer1_base_url": "",
        "layer1_api_key": "",
    }.items():
        monkeypatch.setattr(live.llm, field, value)
    # providers are tagged with the key they were built for; no network
    monkeypatch.setattr(
        client_module,
        "_get_provider",
        lambda base_url, api_key: type("P", (), {"key": api_key})(),
    )
    LLMClient.reset()
    yield live
    LLMClient.reset()


def _chain_model() -> str:
    from services.llm_client import LLMClient

    return LLMClient()._build_fallback_chain(ConfigManager(), "default")[0]["model"]


class TestLLMClientUsesTheRunSnapshot:
    def test_model_saved_mid_run_does_not_cross_runs(self, _llm_live):
        from services.llm_client import LLMClient

        snap = _llm_live.snapshot()  # run A starts with gpt-4o
        _llm_live.llm.model = "gpt-4.1-mini"  # Settings save, same key
        LLMClient.reset()

        with config_module.run_scope(snap):  # run A's next LLM call
            LLMClient()._get_client()
            assert LLMClient().get_layer_config(1).model == "gpt-4o"
            assert _chain_model() == "gpt-4o"
            assert LLMClient()._get_cheap_client()[1] == "gpt-4o"

        # a request / new run after the save, outside run A
        assert LLMClient().get_layer_config(1).model == "gpt-4.1-mini"
        assert _chain_model() == "gpt-4.1-mini"
        assert LLMClient()._get_cheap_client()[1] == "gpt-4.1-mini"

    def test_run_keeps_its_model_when_a_later_request_warms_the_client(
        self, _llm_live
    ):
        from services.llm_client import LLMClient

        snap = _llm_live.snapshot()
        _llm_live.llm.model = "gpt-4.1-mini"
        LLMClient.reset()
        LLMClient()._get_client()  # first use after the save is outside run A

        with config_module.run_scope(snap):
            assert LLMClient().get_layer_config(1).model == "gpt-4o"
            assert _chain_model() == "gpt-4o"

    def test_get_client_returns_the_provider_for_the_callers_key(self, _llm_live):
        from services.llm_client import LLMClient

        snap = _llm_live.snapshot()  # run A: key a
        _llm_live.llm.api_key = "sk-task13-b"  # Settings save: key b

        with config_module.run_scope(snap):
            assert LLMClient()._get_client().key == "sk-task13-a"
        assert LLMClient()._get_client().key == "sk-task13-b"
        with config_module.run_scope(snap):
            assert LLMClient()._get_client().key == "sk-task13-a"


def test_snapshot_cannot_be_saved():
    """A run's snapshot carries per-run overrides; it must never hit disk."""
    snap = ConfigManager().snapshot()
    with pytest.raises(RuntimeError):
        snap.save()
