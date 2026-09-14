"""Regression tests: a run's flags must not outlive the run.

`/api/pipeline/run` writes ~18 fields onto the process-wide ConfigManager
singleton. Nothing put them back, so the flags leaked into every later run in
the process and the next Settings save persisted one run's ad-hoc choices to
data/config.json.

Separately, the L1 consistency block was a chain of `if body.x: cfg.x = True`
with no else, so clearing a checkbox in the UI did nothing.
"""

from config.defaults import PipelineConfig
from api.pipeline_routes import _apply_run_overrides, _restore_run_overrides


class TestOverridesAreReversible:
    def test_apply_returns_the_previous_values(self):
        cfg = PipelineConfig()
        cfg.enable_quality_gate = True

        previous = _apply_run_overrides(cfg, {"enable_quality_gate": False})

        assert previous == {"enable_quality_gate": True}
        assert cfg.enable_quality_gate is False

    def test_restore_puts_every_field_back(self):
        cfg = PipelineConfig()
        original = {
            "enable_quality_gate": cfg.enable_quality_gate,
            "language": cfg.language,
            "smart_revision_threshold": cfg.smart_revision_threshold,
        }

        previous = _apply_run_overrides(
            cfg,
            {
                "enable_quality_gate": not original["enable_quality_gate"],
                "language": "en",
                "smart_revision_threshold": 1.0,
            },
        )
        _restore_run_overrides(cfg, previous)

        for field, value in original.items():
            assert getattr(cfg, field) == value, f"{field} leaked past the run"

    def test_a_second_run_starts_from_the_saved_settings(self):
        """The leak: run 1's flags used to become run 2's starting point."""
        cfg = PipelineConfig()
        cfg.enable_agent_debate = True  # the user's saved setting

        snapshot = _apply_run_overrides(cfg, {"enable_agent_debate": False})
        _restore_run_overrides(cfg, snapshot)

        assert cfg.enable_agent_debate is True

    def test_restore_tolerates_an_empty_snapshot(self):
        cfg = PipelineConfig()
        _restore_run_overrides(cfg, {})
        _restore_run_overrides(cfg, None)


class TestTogglesCanBeTurnedOff:
    """The `if body.x: ... = True` chain could only ever enable a flag."""

    L1_FLAGS = [
        "enable_emotional_memory",
        "enable_proactive_constraints",
        "enable_thread_enforcement",
        "enable_emotional_bridge",
        "enable_scene_beat_writing",
        "enable_l1_causal_graph",
    ]

    def test_master_toggle_enables_the_whole_group(self):
        cfg = PipelineConfig()
        overrides = {name: True for name in self.L1_FLAGS}
        _apply_run_overrides(cfg, overrides)
        assert all(getattr(cfg, name) is True for name in self.L1_FLAGS)

    def test_an_unchecked_flag_is_actually_disabled(self):
        cfg = PipelineConfig()
        for name in self.L1_FLAGS:
            setattr(cfg, name, True)

        _apply_run_overrides(cfg, {name: False for name in self.L1_FLAGS})

        assert all(getattr(cfg, name) is False for name in self.L1_FLAGS), (
            "unchecking a box in the UI had no effect"
        )


def test_run_handler_no_longer_uses_write_only_toggles():
    """Source guard: the write-only `if body.x: ... = True` chain is gone."""
    import api.pipeline_routes as routes

    source = open(routes.__file__, encoding="utf-8").read()
    assert "orch.config.pipeline.enable_emotional_memory = True" not in source
    assert "_restore_run_overrides(orch.config.pipeline" in source
