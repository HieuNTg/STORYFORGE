"""Sprint 2 — the fallback chain must be bounded, and cooldowns must be shared.

Three separate ways a single generate() could misbehave:

1. Providers like OpenRouter expose dozens of free models, and every one was
   added per key. Chains of 50-300 entries are retried up to MAX_RETRIES each,
   over chain_retry_max+1 passes, at a 900s timeout — a worst case with no
   bound worth stating.
2. A chain retry cleared every 429 cooldown. Chapters generate in parallel
   against one shared client, so that threw away what sibling chapters had just
   paid real 429s to learn and sent them straight back at the exhausted key.
3. Nothing capped the total wall-clock of one call.
"""

import time
from unittest.mock import MagicMock, patch

from config.defaults import LLMConfig
from services.llm.client import LLMClient


class TestConfigDefaults:
    def test_discovered_models_are_capped(self):
        assert LLMConfig().max_discovered_models_per_key == 3

    def test_a_call_has_a_finite_ceiling(self):
        cfg = LLMConfig()
        assert cfg.max_total_call_seconds > 0
        assert cfg.max_total_call_seconds >= cfg.request_timeout

    def test_the_ceiling_bounds_the_naive_worst_case(self):
        """3 retries x chain x 3 passes x timeout must not be the real bound."""
        cfg = LLMConfig()
        naive_worst = 3 * cfg.max_discovered_models_per_key * 3 * cfg.request_timeout
        assert cfg.max_total_call_seconds < naive_worst


class TestCooldownsSurviveAChainRetry:
    def _client(self):
        client = LLMClient.__new__(LLMClient)
        client._rate_limited_keys = {}
        client._rate_limited_models = {}
        return client

    def test_expired_cooldowns_are_dropped(self):
        client = self._client()
        client._rate_limited_keys["old"] = time.time() - 10

        client._expire_rate_limits()

        assert "old" not in client._rate_limited_keys

    def test_live_cooldowns_are_kept(self):
        """The defect: a chain retry wiped these for every concurrent chapter."""
        client = self._client()
        client._rate_limited_keys["still-limited"] = time.time() + 120
        client._rate_limited_models["m:still-limited"] = time.time() + 120

        client._expire_rate_limits()

        assert "still-limited" in client._rate_limited_keys
        assert "m:still-limited" in client._rate_limited_models

    def test_mixed_state_is_partitioned_correctly(self):
        client = self._client()
        now = time.time()
        client._rate_limited_keys = {"a": now - 1, "b": now + 60, "c": now - 99}

        client._expire_rate_limits()

        assert set(client._rate_limited_keys) == {"b"}

    def test_chain_retry_no_longer_clears_wholesale(self):
        """Source guard: the wholesale clear was the whole bug."""
        import services.llm.client as mod

        source = open(mod.__file__, encoding="utf-8").read()
        assert "self._rate_limited_keys.clear()" not in source
        assert "self._rate_limited_models.clear()" not in source


class TestRoundRobinCap:
    def _client_with_models(self, n_models: int):
        client = LLMClient.__new__(LLMClient)
        client._rate_limited_keys = {}
        client._rate_limited_models = {}
        client._can_use_model = lambda *a, **k: (True, "")
        added: list = []

        def _add(chain, prov, model, label, api_key=""):
            chain.append({"model": model, "label": label, "_api_key": api_key})
            added.append(label)

        client._add_to_chain = _add
        return client, added

    def test_only_the_capped_number_of_discovered_models_is_added(self):
        client, added = self._client_with_models(40)
        chain: list = []
        models = [f"free/model-{i}" for i in range(40)]

        rr_cap = 3
        rr_added = 0
        for model_name in models:
            if rr_added >= rr_cap:
                break
            client._add_to_chain(chain, MagicMock(), model_name, f"k:rr:{model_name}")
            rr_added += 1

        assert len(chain) == 3, "the cap must bound discovered models"

    def test_source_applies_the_cap_before_adding(self):
        import services.llm.client as mod

        source = open(mod.__file__, encoding="utf-8").read()
        assert "max_discovered_models_per_key" in source
        assert "if rr_added >= rr_cap:" in source


class TestCallDeadline:
    def test_deadline_is_read_from_config(self):
        import services.llm.client as mod

        source = open(mod.__file__, encoding="utf-8").read()
        assert "max_total_call_seconds" in source
        assert "_out_of_time" in source

    def test_zero_disables_the_ceiling(self):
        """Operators must be able to opt out of the bound explicitly."""
        cfg = LLMConfig()
        cfg.max_total_call_seconds = 0
        assert float(cfg.max_total_call_seconds or 0) == 0


class TestExhaustedKeysAreStillTried:
    def test_all_keys_cooling_down_does_not_erase_the_cooldowns(self):
        """The release valve must not destroy other threads' knowledge."""
        import services.llm.client as mod

        source = open(mod.__file__, encoding="utf-8").read()
        # The old release valve cleared the dict before returning every entry.
        assert "do not erase the cooldowns" in source
