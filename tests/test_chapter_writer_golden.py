"""Sprint 3 P8 — Drama-ceiling golden prompt diff.

Locks the exact byte shape of the ## RÀNG BUỘC KỊCH TÍNH directive injected by
P2's build_chapter_prompt. Runs in the default suite (no special marker).

Three snapshots:
1. No contract / drama_ceiling=0  → directive block ABSENT.
2. Full contract with non-empty subtext + forbidden lists → directive PRESENT,
   verbatim text locked byte-for-byte.
3. Empty subtext + empty forbidden → 'không' appears for both fields.

Uses substring match (not full-prompt equality) so surrounding outline/context
variation doesn't break the assertion.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from models.handoff_schemas import NegotiatedChapterContract
from models.schemas import Character, ChapterOutline, WorldSetting
from pipeline.layer1_story.chapter_writer import build_chapter_prompt


# ---------------------------------------------------------------------------
# Minimal stubs — mirror tests/test_chapter_writer.py helpers
# ---------------------------------------------------------------------------

def _mk_config():
    """Minimal pipeline config with all optional features disabled."""
    pipeline = SimpleNamespace(
        rag_enabled=False,
        use_long_context=False,
        enable_voice_lock=False,
        enable_tiered_context=False,
        enable_chapter_contracts=False,
        enable_proactive_constraints=False,
        enable_thread_enforcement=False,
        enable_l1_causal_graph=False,
        enable_emotional_memory=False,
        enable_foreshadowing_enforcement=False,
        enable_scene_decomposition=False,
        enable_scene_beat_writing=False,
        enable_self_review=False,
    )
    return SimpleNamespace(pipeline=pipeline)


def _mk_world():
    return WorldSetting(name="GoldenWorld", description="A world for golden tests")


def _mk_outline(num=1):
    return ChapterOutline(chapter_number=num, title="Chương Vàng", summary="Mọi thứ thay đổi")


def _mk_character():
    return Character(name="Tuấn", role="protagonist", personality="kiên định", background="anh hùng")


def _build_prompt(negotiated_contract=None):
    """Invoke build_chapter_prompt with minimal stubs; returns user_prompt."""
    config = _mk_config()
    with patch("pipeline.layer1_story.chapter_writer.build_adaptive_write_prompt",
               side_effect=lambda p, *a, **kw: p), \
         patch("pipeline.layer1_story.narrative_context_block.build_narrative_block") as mock_nb:
        mock_nb.return_value.render.return_value = ""
        _, user_prompt = build_chapter_prompt(
            config, "Truyện Vàng", "fantasy", "sử thi",
            [_mk_character()], _mk_world(), _mk_outline(), 2000,
            negotiated_contract=negotiated_contract,
        )
    return user_prompt


# ---------------------------------------------------------------------------
# Snapshot 1: No contract → directive ABSENT
# ---------------------------------------------------------------------------

class TestGoldenNoContract:
    def test_directive_absent_when_no_contract(self):
        """No negotiated_contract → ## RÀNG BUỘC KỊCH TÍNH must not appear."""
        prompt = _build_prompt(negotiated_contract=None)
        assert "## RÀNG BUỘC KỊCH TÍNH" not in prompt

    def test_directive_absent_when_ceiling_zero(self):
        """drama_ceiling=0.0 → directive must not appear (zero is falsy guard)."""
        contract = NegotiatedChapterContract(
            chapter_num=1,
            pacing_type="rising",
            drama_target=0.0,
            drama_tolerance=0.10,
            drama_ceiling=0.0,
        )
        prompt = _build_prompt(negotiated_contract=contract)
        assert "## RÀNG BUỘC KỊCH TÍNH" not in prompt


# ---------------------------------------------------------------------------
# Snapshot 2: Full contract → directive present, verbatim byte-locked
# ---------------------------------------------------------------------------

class TestGoldenFullContract:
    """Exact verbatim directive block with non-empty subtext and forbidden lists."""

    _DRAMA_TARGET = 0.65
    _DRAMA_TOLERANCE = 0.10
    _DRAMA_CEILING = 0.75
    _REQUIRED_SUBTEXT = ["bí mật", "phản bội"]
    _FORBIDDEN = ["thuyết minh nội tâm dài"]

    # This is the LOCKED directive shape from P2 commit 4aaa893.
    # Any change to build_chapter_prompt's directive formatting must update this.
    EXPECTED_BLOCK = (
        "## RÀNG BUỘC KỊCH TÍNH\n"
        "- Mục tiêu kịch tính: 0.65\n"
        "- Dung sai: ±0.10\n"
        "- Trần (KHÔNG vượt quá): 0.75\n"
        "- Yêu cầu phụ văn (subtext): bí mật, phản bội\n"
        "- Cấm: thuyết minh nội tâm dài"
    )

    @pytest.fixture(scope="class")
    def prompt(self):
        contract = NegotiatedChapterContract(
            chapter_num=1,
            pacing_type="climax",
            drama_target=self._DRAMA_TARGET,
            drama_tolerance=self._DRAMA_TOLERANCE,
            drama_ceiling=self._DRAMA_CEILING,
            required_subtext=self._REQUIRED_SUBTEXT,
            forbidden_patterns=self._FORBIDDEN,
        )
        return _build_prompt(negotiated_contract=contract)

    def test_directive_block_present(self, prompt):
        assert "## RÀNG BUỘC KỊCH TÍNH" in prompt

    def test_directive_verbatim_shape(self, prompt):
        """Exact byte-for-byte directive block from P2 must appear as substring."""
        assert self.EXPECTED_BLOCK in prompt, (
            f"Expected locked directive block not found in prompt.\n"
            f"Expected:\n{self.EXPECTED_BLOCK!r}\n\n"
            "If P2's build_chapter_prompt changed its directive format, "
            "update EXPECTED_BLOCK here to match the authoritative P2 output."
        )

    def test_drama_target_value(self, prompt):
        assert "Mục tiêu kịch tính: 0.65" in prompt

    def test_drama_tolerance_value(self, prompt):
        assert "Dung sai: ±0.10" in prompt

    def test_drama_ceiling_value(self, prompt):
        assert "Trần (KHÔNG vượt quá): 0.75" in prompt

    def test_required_subtext_values(self, prompt):
        assert "Yêu cầu phụ văn (subtext): bí mật, phản bội" in prompt

    def test_forbidden_patterns_value(self, prompt):
        assert "Cấm: thuyết minh nội tâm dài" in prompt


# ---------------------------------------------------------------------------
# Snapshot 3: Empty subtext + empty forbidden → "không" rendered for both
# ---------------------------------------------------------------------------

class TestGoldenEmptyLists:
    """Empty required_subtext and forbidden_patterns → both render as 'không'."""

    @pytest.fixture(scope="class")
    def prompt(self):
        contract = NegotiatedChapterContract(
            chapter_num=1,
            pacing_type="cooldown",
            drama_target=0.5,
            drama_tolerance=0.10,
            drama_ceiling=0.60,
            required_subtext=[],
            forbidden_patterns=[],
        )
        return _build_prompt(negotiated_contract=contract)

    def test_directive_present(self, prompt):
        assert "## RÀNG BUỘC KỊCH TÍNH" in prompt

    def test_subtext_renders_khong(self, prompt):
        """Empty subtext list → 'subtext): không' in directive."""
        assert "subtext): không" in prompt

    def test_forbidden_renders_khong(self, prompt):
        """Empty forbidden list → 'Cấm: không' in directive."""
        assert "Cấm: không" in prompt

    def test_both_khong_appear_in_directive_section(self, prompt):
        """Both empty fields render 'không' in the directive block (not elsewhere)."""
        idx = prompt.find("## RÀNG BUỘC KỊCH TÍNH")
        assert idx != -1
        directive_section = prompt[idx:]
        assert directive_section.count("không") >= 2
