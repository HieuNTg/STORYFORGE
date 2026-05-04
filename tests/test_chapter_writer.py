"""Tests for chapter_writer directive injection (Sprint 3 P2)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from models.handoff_schemas import NegotiatedChapterContract
from models.schemas import Character, ChapterOutline, WorldSetting
from pipeline.layer1_story.chapter_writer import build_chapter_prompt


def _mk_config():
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
    return WorldSetting(name="TestWorld", description="A test world")


def _mk_outline(num=1):
    return ChapterOutline(chapter_number=num, title="Chapter One", summary="Things happen")


def _mk_character():
    return Character(name="Hùng", role="protagonist", personality="brave", background="hero")


def _mk_contract(drama_target=0.7, drama_tolerance=0.15, drama_ceiling=0.85,
                  required_subtext=None, forbidden_patterns=None):
    return NegotiatedChapterContract(
        chapter_num=1,
        pacing_type="rising",
        drama_target=drama_target,
        drama_tolerance=drama_tolerance,
        drama_ceiling=drama_ceiling,
        required_subtext=required_subtext or [],
        forbidden_patterns=forbidden_patterns or [],
    )


def _build(negotiated_contract=None):
    config = _mk_config()
    outline = _mk_outline()
    world = _mk_world()
    characters = [_mk_character()]

    with patch("pipeline.layer1_story.chapter_writer.build_adaptive_write_prompt", side_effect=lambda p, *a, **kw: p), \
         patch("pipeline.layer1_story.narrative_context_block.build_narrative_block") as mock_nb:
        mock_nb.return_value.render.return_value = ""
        _, user_prompt = build_chapter_prompt(
            config, "Story", "fantasy", "vivid",
            characters, world, outline, 2000,
            negotiated_contract=negotiated_contract,
        )
    return user_prompt


class TestDramaDirectiveInjection:
    def test_directive_present_when_ceiling_positive(self):
        contract = _mk_contract(drama_target=0.7, drama_tolerance=0.15, drama_ceiling=0.85)
        prompt = _build(negotiated_contract=contract)
        assert "## RÀNG BUỘC KỊCH TÍNH" in prompt
        assert "0.70" in prompt
        assert "0.85" in prompt

    def test_directive_absent_when_no_contract(self):
        prompt = _build(negotiated_contract=None)
        assert "## RÀNG BUỘC KỊCH TÍNH" not in prompt

    def test_directive_absent_when_ceiling_zero(self):
        contract = _mk_contract(drama_target=0.0, drama_tolerance=0.15, drama_ceiling=0.0)
        prompt = _build(negotiated_contract=contract)
        assert "## RÀNG BUỘC KỊCH TÍNH" not in prompt

    def test_directive_fields_correct(self):
        contract = _mk_contract(
            drama_target=0.6, drama_tolerance=0.10, drama_ceiling=0.70,
            required_subtext=["betrayal", "regret"],
            forbidden_patterns=["sudden_death"],
        )
        prompt = _build(negotiated_contract=contract)
        assert "Mục tiêu kịch tính: 0.60" in prompt
        assert "Dung sai: ±0.10" in prompt
        assert "Trần (KHÔNG vượt quá): 0.70" in prompt
        assert "betrayal, regret" in prompt
        assert "sudden_death" in prompt

    def test_empty_lists_show_khong(self):
        contract = _mk_contract(required_subtext=[], forbidden_patterns=[])
        prompt = _build(negotiated_contract=contract)
        # Both empty → "không" appears twice in the directive block
        directive_start = prompt.find("## RÀNG BUỘC KỊCH TÍNH")
        assert directive_start != -1
        directive_section = prompt[directive_start:]
        assert directive_section.count("không") >= 2

    def test_golden_diff_only_directive(self):
        """Directive is the only diff between with- and without-contract prompts."""
        contract = _mk_contract(drama_target=0.5, drama_tolerance=0.15, drama_ceiling=0.65)
        prompt_with = _build(negotiated_contract=contract)
        prompt_without = _build(negotiated_contract=None)

        # Reconstruct expected directive block
        directive = (
            "\n\n## RÀNG BUỘC KỊCH TÍNH"
            "\n- Mục tiêu kịch tính: 0.50"
            "\n- Dung sai: ±0.15"
            "\n- Trần (KHÔNG vượt quá): 0.65"
            "\n- Yêu cầu phụ văn (subtext): không"
            "\n- Cấm: không"
        )
        # The with-contract prompt equals without-contract + directive + Vietnamese reminder
        vn_reminder = "\n\n[NHẮC LẠI: Viết hoàn toàn bằng tiếng Việt. Không dùng tiếng Anh hay ngôn ngữ khác.]"
        assert prompt_with == prompt_without.replace(
            vn_reminder, directive + vn_reminder
        )

    def test_token_budget_under_80(self):
        """Directive must add ≤ 80 tokens (estimated as len//4)."""
        contract = _mk_contract(
            required_subtext=["item1", "item2"],
            forbidden_patterns=["pat1", "pat2", "pat3"],
        )
        prompt_with = _build(negotiated_contract=contract)
        prompt_without = _build(negotiated_contract=None)
        directive_len = len(prompt_with) - len(prompt_without)
        estimated_tokens = directive_len // 4
        assert estimated_tokens <= 80, f"Directive ~{estimated_tokens} tokens exceeds 80-token budget"
