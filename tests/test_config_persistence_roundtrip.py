"""Regression tests: config must survive a save/load round-trip intact.

`save_config` wrote a hand-maintained dict that had drifted to 103 of 244
dataclass fields. Everything else — all 26 l2_* knobs, the per-run budget caps,
chapter_batch_size, parallel_chapters_enabled — reverted to code defaults on
restart. And because the writer replaced the file wholesale, any key it did not
list was deleted on the next save, including tuned values written by an older
build.
"""

import dataclasses
import json
import os

import pytest

import config.persistence as persistence
from config.defaults import LLMConfig, PipelineConfig


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(persistence, "CONFIG_FILE", str(path))
    return path


class TestEveryFieldIsPersisted:
    def test_all_llm_fields_round_trip(self, sandbox):
        persistence.save_config(LLMConfig(), PipelineConfig())
        saved = json.loads(sandbox.read_text(encoding="utf-8"))["llm"]

        expected = {f.name for f in dataclasses.fields(LLMConfig)}
        assert expected - saved.keys() == set(), "fields silently lost on save"

    def test_all_pipeline_fields_round_trip_except_derived(self, sandbox):
        persistence.save_config(LLMConfig(), PipelineConfig())
        saved = json.loads(sandbox.read_text(encoding="utf-8"))["pipeline"]

        expected = {f.name for f in dataclasses.fields(PipelineConfig)}
        missing = expected - saved.keys()
        # `voice` is a derived nested view rebuilt by __post_init__.
        assert missing == {"voice"}, f"unexpectedly missing: {missing - {'voice'}}"

    @pytest.mark.parametrize(
        "field_name",
        [
            "l2_contract_gate",
            "enable_agent_debate",
            "max_debate_rounds",
            "parallel_chapters_enabled",
            "chapter_batch_size",
            "debate_mode",
        ],
    )
    def test_named_field_survives_a_restart(self, sandbox, field_name):
        """Each of these used to revert to its code default on every restart."""
        llm, pipeline = LLMConfig(), PipelineConfig()
        original = getattr(pipeline, field_name)
        flipped = (
            not original
            if isinstance(original, bool)
            else (original + 1 if isinstance(original, int) else "lite")
        )
        setattr(pipeline, field_name, flipped)

        persistence.save_config(llm, pipeline)

        reloaded_llm, reloaded_pipeline = LLMConfig(), PipelineConfig()
        persistence.load_config(reloaded_llm, reloaded_pipeline)
        assert getattr(reloaded_pipeline, field_name) == flipped


class TestUnknownKeysAreNotDestroyed:
    def test_unknown_pipeline_key_survives_a_save(self, sandbox):
        sandbox.write_text(
            json.dumps({"pipeline": {"enable_consistency_rewrite": True}}),
            encoding="utf-8",
        )

        persistence.save_config(LLMConfig(), PipelineConfig())

        saved = json.loads(sandbox.read_text(encoding="utf-8"))
        assert saved["pipeline"]["enable_consistency_rewrite"] is True

    def test_unknown_top_level_key_survives_a_save(self, sandbox):
        sandbox.write_text(json.dumps({"custom_section": {"a": 1}}), encoding="utf-8")

        persistence.save_config(LLMConfig(), PipelineConfig())

        saved = json.loads(sandbox.read_text(encoding="utf-8"))
        assert saved["custom_section"] == {"a": 1}

    def test_a_corrupt_existing_file_does_not_block_saving(self, sandbox):
        sandbox.write_text("{not json", encoding="utf-8")

        persistence.save_config(LLMConfig(), PipelineConfig())

        saved = json.loads(sandbox.read_text(encoding="utf-8"))
        assert "llm" in saved and "pipeline" in saved


class TestEnvOverridesDoNotOverwriteStoredChoices:
    """An env override wins at runtime but must never be written to disk.

    Found while running the Sprint 1 test plan: `.env` carried
    STORYFORGE_MODEL=gemini-… from the era when env overrides were inert, while
    the user had chosen `model: "auto"` (rotate Gemini/Qwen) in Settings. With
    overrides live and save_config writing every field, saving any unrelated
    setting would have baked the env value into config.json permanently —
    outliving the env var itself.
    """

    def test_env_value_is_active_in_memory(self, sandbox, monkeypatch):
        sandbox.write_text(json.dumps({"llm": {"model": "auto"}}), encoding="utf-8")
        monkeypatch.setenv("STORYFORGE_MODEL", "gemini-forced")

        llm, pipeline = LLMConfig(), PipelineConfig()
        persistence.load_config(llm, pipeline)

        assert llm.model == "gemini-forced"

    def test_env_value_is_not_written_back(self, sandbox, monkeypatch):
        sandbox.write_text(json.dumps({"llm": {"model": "auto"}}), encoding="utf-8")
        monkeypatch.setenv("STORYFORGE_MODEL", "gemini-forced")

        llm, pipeline = LLMConfig(), PipelineConfig()
        persistence.load_config(llm, pipeline)
        persistence.save_config(llm, pipeline)

        saved = json.loads(sandbox.read_text(encoding="utf-8"))
        assert saved["llm"]["model"] == "auto", "env value leaked into the file"

    def test_non_overridden_fields_still_persist(self, sandbox, monkeypatch):
        """The exclusion must be surgical, not a blanket skip."""
        sandbox.write_text(json.dumps({"llm": {"model": "auto"}}), encoding="utf-8")
        monkeypatch.setenv("STORYFORGE_MODEL", "gemini-forced")

        llm, pipeline = LLMConfig(), PipelineConfig()
        persistence.load_config(llm, pipeline)
        llm.max_tokens = 12345
        persistence.save_config(llm, pipeline)

        saved = json.loads(sandbox.read_text(encoding="utf-8"))
        assert saved["llm"]["max_tokens"] == 12345

    def test_clearing_the_env_var_restores_the_stored_choice(
        self, sandbox, monkeypatch
    ):
        sandbox.write_text(json.dumps({"llm": {"model": "auto"}}), encoding="utf-8")
        monkeypatch.setenv("STORYFORGE_MODEL", "gemini-forced")
        llm, pipeline = LLMConfig(), PipelineConfig()
        persistence.load_config(llm, pipeline)
        persistence.save_config(llm, pipeline)

        monkeypatch.delenv("STORYFORGE_MODEL")
        llm2, pipeline2 = LLMConfig(), PipelineConfig()
        persistence.load_config(llm2, pipeline2)

        assert llm2.model == "auto"


class TestDefaultsHaveOneSourceOfTruth:
    """The GET surface used to restate defaults via getattr and contradict them."""

    @pytest.mark.parametrize(
        "field_name",
        [
            "enable_pipeline_overlay",
            "enable_chapter_illustration",
            "enable_simulation_transcript",
            "comic_shot_list_enabled",
            "comic_compositor_enabled",
            "panels_max",
            "flowkit_enabled",
            "flowkit_aspect_ratio",
        ],
    )
    def test_api_reports_the_dataclass_default(self, field_name):
        import api.config_routes as routes

        source = open(routes.__file__, encoding="utf-8").read()
        assert (
            f'getattr(cfg.pipeline, "{field_name}"' not in source
        ), f"{field_name} still restates a default in the API layer"

    def test_config_routes_has_no_pipeline_getattr_defaults(self):
        import api.config_routes as routes

        source = open(routes.__file__, encoding="utf-8").read()
        assert "getattr(cfg.pipeline," not in source
        assert "getattr(cfg.llm," not in source


def test_save_does_not_write_outside_the_sandbox(sandbox):
    """Guards the test suite itself: saves must not touch the real config."""
    persistence.save_config(LLMConfig(), PipelineConfig())
    assert os.path.exists(sandbox)
