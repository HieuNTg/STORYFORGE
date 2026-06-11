"""Unit tests for pipeline.layer1_story.chapter_contract_setup.

Covers the shared contract-build helper extracted from batch_generator's
sequential and parallel write paths: flag gating, proactive constraints,
override formatting, and best-effort failure handling.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from pipeline.layer1_story.chapter_contract_setup import build_contract_for_chapter


def _config(contracts: bool = True, proactive: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            enable_chapter_contracts=contracts,
            enable_proactive_constraints=proactive,
        )
    )


def _outline(num: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        chapter_number=num,
        characters_involved=[],
        pacing_type="rising",
        emotional_arc="",
    )


def _call(config, **overrides):
    kwargs = dict(
        threads=[],
        macro_arcs=None,
        conflicts=None,
        foreshadowing_plan=None,
        characters=[],
    )
    kwargs.update(overrides)
    return build_contract_for_chapter(config, _outline(), **kwargs)


class TestFlagGating:
    def test_disabled_flag_returns_none(self):
        contract, text = _call(_config(contracts=False))
        assert contract is None
        assert text == ""

    def test_enabled_flag_builds_contract(self):
        contract, text = _call(_config())
        assert contract is not None
        assert contract.chapter_number == 1
        assert text != ""


class TestProactiveConstraints:
    def test_secrets_forwarded_when_proactive_enabled(self):
        draft = SimpleNamespace(world=SimpleNamespace(rules=["không dùng súng"]))
        characters = [SimpleNamespace(name="Lý Huyền", secret="thân thế thật")]
        contract, _ = _call(
            _config(proactive=True),
            characters=characters,
            draft=draft,
            include_proactive=True,
        )
        assert contract.world_rules == ["không dùng súng"]
        assert contract.secret_protection == {"Lý Huyền": "thân thế thật"}

    def test_proactive_skipped_without_flag(self):
        draft = SimpleNamespace(world=SimpleNamespace(rules=["không dùng súng"]))
        contract, _ = _call(
            _config(proactive=False), draft=draft, include_proactive=True
        )
        assert contract.world_rules == []


class TestOverrideContract:
    def test_override_skips_build_and_formats(self):
        contract, _ = _call(_config())
        with patch(
            "pipeline.layer1_story.chapter_contract_builder.build_contract"
        ) as mock_build:
            result, text = _call(_config(), override_contract=contract)
            mock_build.assert_not_called()
        assert result is contract
        assert text != ""

    def test_override_formats_even_when_flag_disabled(self):
        contract, _ = _call(_config())
        result, text = _call(_config(contracts=False), override_contract=contract)
        assert result is contract
        assert text != ""


class TestBestEffortFailure:
    def test_build_failure_returns_none_and_logs(self, caplog):
        with patch(
            "pipeline.layer1_story.chapter_contract_builder.build_contract",
            side_effect=RuntimeError("boom"),
        ):
            contract, text = _call(_config())
        assert contract is None
        assert text == ""
        assert any("non-fatal" in r.message for r in caplog.records)
