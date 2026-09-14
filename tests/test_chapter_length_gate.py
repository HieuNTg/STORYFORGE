"""Tests for the chapter length gate.

Context: `word_count` reached the model as one soft bullet and nothing compared
the result against it. A 10-chapter run with a 2000-word target produced
min 884 / mean 1450 / max 1895, with 9 of 10 chapters ending on a complete
sentence — i.e. the model stopped early rather than being truncated, so raising
`max_tokens` could not help. This gate measures and asks for one expansion.

The failure paths matter as much as the happy one: this runs on every chapter of
every story, so it must never break generation and must never accept an
"expansion" that is really a summary.
"""

from types import SimpleNamespace

from pipeline.layer1_story.chapter_length_gate import expand_chapter_if_short


class _Chapter:
    def __init__(self, content: str):
        self.content = content
        self.word_count = len(content.split())


def _words(n: int) -> str:
    return " ".join(["tu"] * n)


def _outline():
    return SimpleNamespace(chapter_number=3)


def _config(**kw):
    base = {"enable_length_gate": True, "length_gate_min_ratio": 0.85}
    base.update(kw)
    return SimpleNamespace(**base)


class _LLM:
    """Returns a fixed word count; records whether it was called at all."""

    def __init__(self, words: int):
        self._words = words
        self.called = False

    def generate(self, **kwargs):
        self.called = True
        return _words(self._words)


class _ExplodingLLM:
    def generate(self, **kwargs):
        raise RuntimeError("bridge down")


def test_chapter_at_target_is_left_alone():
    llm = _LLM(9999)
    ch = _Chapter(_words(1800))  # 90% of target, above the 85% floor
    expand_chapter_if_short(_config(), llm, ch, _outline(), 2000)
    assert ch.word_count == 1800
    assert not llm.called, "must not spend an LLM call on a chapter already long enough"


def test_short_chapter_is_expanded():
    ch = _Chapter(_words(900))  # 45% of target — the case that motivated this
    expand_chapter_if_short(_config(), _LLM(2050), ch, _outline(), 2000)
    assert ch.word_count == 2050
    assert ch.content.split()[0] == "tu"


def test_expansion_that_came_back_shorter_is_rejected():
    """A 'rewrite' that shortens has replaced the chapter with a summary of
    itself — the very failure this gate exists to prevent."""
    original = _words(900)
    ch = _Chapter(original)
    expand_chapter_if_short(_config(), _LLM(400), ch, _outline(), 2000)
    assert ch.word_count == 900
    assert ch.content == original


def test_llm_failure_is_non_fatal():
    original = _words(900)
    ch = _Chapter(original)
    expand_chapter_if_short(_config(), _ExplodingLLM(), ch, _outline(), 2000)
    assert ch.content == original


def test_gate_can_be_disabled():
    llm = _LLM(9999)
    ch = _Chapter(_words(100))
    expand_chapter_if_short(_config(enable_length_gate=False), llm, ch, _outline(), 2000)
    assert ch.word_count == 100
    assert not llm.called


def test_missing_or_zero_target_is_a_noop():
    llm = _LLM(9999)
    ch = _Chapter(_words(100))
    expand_chapter_if_short(_config(), llm, ch, _outline(), 0)
    assert ch.word_count == 100
    assert not llm.called


class TestStreamTimeoutsComeFromConfig:
    """The first-chunk ceiling used to be hard-coded at 60s in two places.

    A reasoning model spends its time-to-first-token thinking before it emits
    anything: measured median 51.6s and max 106.3s for qwen3.8-max-thinking
    through the local bridge. At 60s a large share of calls were killed
    mid-thought and retried from scratch — paying the wait twice and silently
    demoting the request to the next model in the chain, i.e. defeating the
    caller's model choice.
    """

    def test_config_values_reach_the_stream_wrapper(self):
        from unittest.mock import patch
        from services.llm_client import LLMClient
        from config import ConfigManager

        captured = {}

        def fake_wrap(self, gen, chunk_timeout=30, first_chunk_timeout=60):
            captured["chunk"] = chunk_timeout
            captured["first"] = first_chunk_timeout
            yield "x"

        cfg = ConfigManager().load()
        client = LLMClient()
        with patch.object(type(client), "_stream_with_chunk_timeout", fake_wrap):
            try:
                list(client.generate_stream(system_prompt="s", user_prompt="u"))
            except Exception:
                pass  # the chain may have no usable provider in tests

        assert captured.get("first") == cfg.pipeline.stream_first_chunk_timeout
        assert captured.get("chunk") == cfg.pipeline.stream_chunk_timeout

    def test_first_chunk_ceiling_clears_observed_reasoning_latency(self):
        """Guard the default against being tuned back below what we measured."""
        from config import ConfigManager

        cfg = ConfigManager().load()
        # 106.3s was the slowest observed call; the ceiling must clear it with
        # room for longer prompts, or reasoning models get cut off again.
        assert cfg.pipeline.stream_first_chunk_timeout > 110


# ---------------------------------------------------------------------------
# Reach: the gate's knobs must survive a restart and be reachable from the UI.
# They shipped as code defaults only, so a change never persisted.
# ---------------------------------------------------------------------------


def test_length_gate_knobs_survive_a_restart(tmp_path):
    import os
    from unittest.mock import patch

    from config.defaults import LLMConfig, PipelineConfig
    from config.persistence import load_config, save_config

    config_file = os.path.join(tmp_path, "config.json")
    with patch("config.persistence.CONFIG_FILE", config_file):
        pipeline = PipelineConfig(
            enable_length_gate=False,
            length_gate_min_ratio=0.7,
            stream_first_chunk_timeout=240,
        )
        save_config(LLMConfig(), pipeline)

        restored = PipelineConfig()
        load_config(LLMConfig(), restored)

    assert restored.enable_length_gate is False
    assert restored.length_gate_min_ratio == 0.7
    assert restored.stream_first_chunk_timeout == 240


def test_length_gate_knobs_are_exposed_by_the_config_api():
    """The Settings UI can only show what GET /api/config returns."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.config_routes import router

    app = FastAPI()
    app.include_router(router, prefix="/api")
    body = TestClient(app).get("/api/config").json()["pipeline"]
    for key in (
        "enable_length_gate",
        "length_gate_min_ratio",
        "stream_first_chunk_timeout",
        "stream_chunk_timeout",
    ):
        assert key in body, key
