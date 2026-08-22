"""Regression tests: the LLM cache key must identify the request.

Two bugs sat in the same few lines.

The read key used `config.llm.model` regardless of the `model` argument, so
every layer shared one namespace — and `generate_for_layer` delegates with
`model=layer2_model`, which meant a layer-2 call could be served a cached
layer-1 body. The write key used whichever model actually answered, so anything
served by a fallback landed under a key no read ever computes and could never
hit. `max_tokens` was absent entirely, so a 512-token answer was replayed for an
8192-token request.
"""

from services.llm_cache import LLMCache


def _params(**over):
    base = dict(
        system_prompt="sys",
        user_prompt="viết chương 1",
        model="primary-model",
        temperature=0.8,
        json_mode=False,
        max_tokens=4096,
        model_tier="default",
    )
    base.update(over)
    return base


class TestKeyIdentity:
    def test_same_request_yields_the_same_key(self):
        cache = LLMCache(ttl_days=1)
        assert cache._make_key(**_params()) == cache._make_key(**_params())

    def test_different_model_yields_a_different_key(self):
        """Layer isolation: layer 2 must not read layer 1's entry."""
        cache = LLMCache(ttl_days=1)
        assert cache._make_key(**_params(model="layer1-model")) != cache._make_key(
            **_params(model="layer2-model")
        )

    def test_different_max_tokens_yields_a_different_key(self):
        cache = LLMCache(ttl_days=1)
        assert cache._make_key(**_params(max_tokens=512)) != cache._make_key(
            **_params(max_tokens=8192)
        )

    def test_different_tier_yields_a_different_key(self):
        cache = LLMCache(ttl_days=1)
        assert cache._make_key(**_params(model_tier="cheap")) != cache._make_key(
            **_params(model_tier="default")
        )


class TestClientCacheWiring:
    """Source guards — the two lines that produced the mismatch."""

    def _source(self) -> str:
        import services.llm.client as client

        return open(client.__file__, encoding="utf-8").read()

    def test_read_key_uses_the_requested_model(self):
        assert "effective_model = model or config.llm.model" in self._source()

    def test_write_key_is_not_rewritten_to_the_responding_model(self):
        source = self._source()
        assert '{**cache_params, "model": actual_model}' not in source
        assert "cache.put(result, **cache_params)" in source

    def test_cache_params_carry_max_tokens_and_tier(self):
        source = self._source()
        assert "max_tokens=max_tokens or config.llm.max_tokens" in source
        assert "model_tier=model_tier," in source


class TestRoundTrip:
    def test_a_stored_entry_is_readable_with_the_same_params(self, tmp_path):
        cache = LLMCache(ttl_days=1, db_path=str(tmp_path / "c.db"))
        cache.put("nội dung chương", **_params())
        assert cache.get(**_params()) == "nội dung chương"

    def test_a_layer2_request_does_not_read_the_layer1_entry(self, tmp_path):
        cache = LLMCache(ttl_days=1, db_path=str(tmp_path / "c.db"))
        cache.put("bản L1", **_params(model="layer1-model"))
        assert cache.get(**_params(model="layer2-model")) is None
