"""Sprint 2 — three ways a cheap-tier call could fail or spin for no reason.

1. Building a cheap-tier chain set `cheap_model_name`, and the primary-model
   block was guarded by `if cheap_model_name is None`. So every cheap-tier call
   — JSON repair, forge, character traits — had a chain with no primary in it
   at all, and died outright whenever the cheap provider was down, however
   healthy the model the operator actually configured.

2. `generate_json` gave its shape-mismatch retry a fresh LLM-repair budget, so
   one call could traverse the whole fallback chain four times (main + repair,
   then retry + repair) before raising.

3. Quality-gate retries re-issue a prompt that is often byte-identical to the
   one that just failed — a contract rebuild that raised, or a rebuild with an
   empty failure list. The cache then served the rejected body back and every
   remaining retry was a guaranteed no-op.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


def _make_llm_config(
    model="gpt-4",
    cheap_model="",
    cheap_base_url="",
    base_url="http://api.test",
):
    cfg = MagicMock()
    cfg.llm.api_key = "key"
    cfg.llm.base_url = base_url
    cfg.llm.model = model
    cfg.llm.cheap_model = cheap_model
    cfg.llm.cheap_base_url = cheap_base_url
    cfg.llm.fallback_models = []
    cfg.llm.temperature = 0.7
    cfg.llm.max_tokens = 2000
    cfg.llm.cache_enabled = False
    cfg.llm.cache_ttl_days = 7
    cfg.pipeline.language = "vi"
    cfg.pipeline.share_base_url = ""
    return cfg


def _client(cfg):
    from services.llm_client import LLMClient

    LLMClient._instance = None
    with patch("services.llm_client.ConfigManager", return_value=cfg), patch(
        "services.llm_client.OpenAI"
    ):
        client = LLMClient()
    client._current_model = cfg.llm.model
    client._client = MagicMock()
    client._last_key = "http://api.test:key"
    # _get_cheap_client reads the live ConfigManager, not the mock passed to
    # _build_fallback_chain, so pin it to keep the assertions about ordering.
    if cfg.llm.cheap_model:
        client._get_cheap_client = lambda: (MagicMock(), cfg.llm.cheap_model)
    return client


def _labels(chain):
    return [c["label"] for c in chain]


@pytest.fixture(autouse=True)
def _reset_singleton():
    from services import llm_client

    llm_client.LLMClient._instance = None
    yield
    llm_client.LLMClient._instance = None


class TestCheapTierKeepsThePrimaryAsLastResort:
    def _chain(self):
        cfg = _make_llm_config(
            cheap_model="gpt-3.5-turbo", cheap_base_url="http://cheap.test"
        )
        return _client(cfg)._build_fallback_chain(cfg, "cheap")

    def test_the_primary_model_is_in_the_chain(self):
        """The defect: a healthy primary was excluded outright."""
        assert "gpt-4" in [c["model"] for c in self._chain()]

    def test_the_cheap_model_still_goes_first(self):
        assert self._chain()[0]["model"] == "gpt-3.5-turbo"

    def test_the_primary_goes_last_so_cost_ordering_holds(self):
        chain = self._chain()
        assert chain[-1]["model"] == "gpt-4"
        assert chain[-1]["label"].startswith("last-resort")

    def test_a_dead_cheap_provider_no_longer_empties_the_chain(self):
        chain = self._chain()
        assert len(chain) >= 2, "one entry means one point of failure"

    def test_the_primary_is_not_duplicated(self):
        models = [c["model"] for c in self._chain()]
        assert models.count("gpt-4") == 1


class TestDefaultTierIsUnchanged:
    def test_primary_still_leads_and_cheap_still_trails(self):
        cfg = _make_llm_config(
            cheap_model="gpt-3.5-turbo", cheap_base_url="http://cheap.test"
        )
        chain = _client(cfg)._build_fallback_chain(cfg, "default")
        assert chain[0]["model"] == "gpt-4"
        assert chain[-1]["model"] == "gpt-3.5-turbo"

    def test_no_cheap_model_configured_yields_no_last_resort_entry(self):
        cfg = _make_llm_config()
        chain = _client(cfg)._build_fallback_chain(cfg, "cheap")
        assert not any(c["label"].startswith("last-resort") for c in chain)


class _Recorder:
    """A GenerationMixin host that counts calls instead of making them."""

    def __init__(self, main_text: str):
        self.main_text = main_text
        self.main_calls = 0
        self.repair_calls = 0

    def _generate_json_text(self, *a, **k):
        self.main_calls += 1
        return self.main_text

    def generate(self, *a, **k):
        """The repair model returns parseable JSON of the wrong shape.

        That is what drives the shape-mismatch retry: a first pass that stays
        unparseable raises before the retry is ever reached, so it cannot show
        whether the retry gets its own repair budget.
        """
        self.repair_calls += 1
        return "[1, 2]"


def _subject(main_text: str):
    from services.llm.generation import GenerationMixin

    class Subject(_Recorder, GenerationMixin):
        pass

    return Subject(main_text)


class TestRepairBudgetIsPerCall:
    def test_a_shape_retry_does_not_get_a_second_repair_pass(self):
        """The defect: 2 main + 2 repair = 4 chain traversals for one call."""
        subject = _subject("not json at all, just prose")

        with pytest.raises(ValueError):
            subject.generate_json("sys", "user", expect="dict")

        assert subject.repair_calls == 1, (
            f"{subject.repair_calls} LLM repair passes for one generate_json"
        )

    def test_the_shape_retry_still_happens(self):
        subject = _subject("not json at all, just prose")

        with pytest.raises(ValueError):
            subject.generate_json("sys", "user", expect="dict")

        assert subject.main_calls == 2, "the shape-mismatch retry must still run"

    def test_a_single_pass_still_gets_its_one_repair(self):
        """The budget bounds repairs; it must not remove the first one."""
        subject = _subject("not json at all, just prose")

        assert subject.generate_json("sys", "user") == [1, 2]
        assert subject.repair_calls == 1

    def test_valid_json_never_touches_the_repair_path(self):
        subject = _subject(json.dumps({"ok": True}))

        assert subject.generate_json("sys", "user", expect="dict") == {"ok": True}
        assert subject.repair_calls == 0


class TestNoCacheReads:
    def test_the_flag_is_scoped_to_the_block(self):
        from services.llm.client import _cache_reads_enabled, no_cache_reads

        assert _cache_reads_enabled.get() is True
        with no_cache_reads():
            assert _cache_reads_enabled.get() is False
        assert _cache_reads_enabled.get() is True

    def test_the_flag_is_restored_after_an_exception(self):
        from services.llm.client import _cache_reads_enabled, no_cache_reads

        with pytest.raises(RuntimeError):
            with no_cache_reads():
                raise RuntimeError("rewrite blew up")
        assert _cache_reads_enabled.get() is True

    def test_a_sibling_task_is_not_affected(self):
        """One chapter entering a retry must not disable the whole run's cache."""
        import asyncio

        from services.llm.client import _cache_reads_enabled, no_cache_reads

        async def retrying():
            with no_cache_reads():
                await asyncio.sleep(0.01)
                return _cache_reads_enabled.get()

        async def sibling():
            await asyncio.sleep(0.005)
            return _cache_reads_enabled.get()

        async def main():
            return await asyncio.gather(retrying(), sibling())

        assert asyncio.run(main()) == [False, True]


class TestRetryPathsUseIt:
    """Source guards: the mechanism is worthless if the retries don't call it."""

    def test_the_sequential_contract_retry_suppresses_reads(self):
        import pipeline.layer1_story.contract_validation_retry as mod

        source = open(mod.__file__, encoding="utf-8").read()
        assert "with no_cache_reads():" in source

    def test_the_threaded_batch_retry_suppresses_reads(self):
        import pipeline.layer1_story.contract_batch_retry as mod

        source = open(mod.__file__, encoding="utf-8").read()
        assert "with no_cache_reads():" in source
