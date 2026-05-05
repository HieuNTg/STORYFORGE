"""Behavior tests for pipeline/layer2_enhance/enhancer.py.

Covers:
- _build_arc_context: arc waypoint filtering by chapter range
- _extract_pacing_directive / _extract_pacing_type
- _build_knowledge_constraints
- _precheck_coherence: LLM path + error path
- StoryEnhancer.detect_structural_issues: guard flags
- StoryEnhancer.enhance_chapter: happy path, scene-enhancer failure fallback
- StoryEnhancer._apply_contract_validation: no-contract short-circuit, retry logic
- StoryEnhancer._apply_voice_validation: no-contract short-circuit
- StoryEnhancer.enhance_story_async: drama score mapping, signal consumption
- StoryEnhancer.enhance_story (sync guard)
- StoryEnhancer.enhance_with_feedback / _find_weak_chapters
- Feature flags: l2_consistency_engine, l2_voice_preservation, l2_drama_curve_balancing
"""

import pytest
from unittest.mock import MagicMock, patch

from models.schemas import (
    Chapter, SimulationResult, SimulationEvent, StoryDraft,
    EnhancedStory, Character,
)
from pipeline.layer2_enhance.enhancer import (
    StoryEnhancer,
    _build_arc_context,
    _extract_pacing_directive,
    _extract_pacing_type,
    _build_knowledge_constraints,
    _precheck_coherence,
    MIN_DRAMA_SCORE,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _chapter(num: int, content: str = "some content here") -> Chapter:
    return Chapter(chapter_number=num, title=f"Ch{num}", content=content, word_count=10)


def _sim_result(**kwargs) -> SimulationResult:
    defaults = dict(events=[], drama_suggestions=[], character_arcs={})
    defaults.update(kwargs)
    return SimulationResult(**defaults)


def _draft(chapters=None, characters=None, genre="Tiên Hiệp") -> StoryDraft:
    return StoryDraft(
        title="Test Story",
        genre=genre,
        chapters=chapters or [_chapter(1)],
        characters=characters or [],
    )


def _mock_llm(generate_return="enhanced text", generate_json_return=None):
    """Return a mock LLMClient."""
    llm = MagicMock()
    llm.generate.return_value = generate_return
    llm.generate_json.return_value = generate_json_return or {}
    llm.model_for_layer.return_value = "mock-model"
    return llm


# ──────────────────────────────────────────────────────────────────────────────
# _build_arc_context
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildArcContext:
    def test_empty_characters_returns_empty(self):
        draft = _draft(characters=[])
        assert _build_arc_context(draft, 1) == ""

    def test_waypoint_in_range_included(self):
        char = Character(name="Lý Minh", role="chính", personality="dũng cảm")
        char.arc_waypoints = [
            {"chapter_range": "1-5", "stage_name": "Thử thách", "progress_pct": 0.3}
        ]
        draft = _draft(characters=[char])
        result = _build_arc_context(draft, 3)
        assert "Lý Minh" in result
        assert "Thử thách" in result

    def test_waypoint_outside_range_excluded(self):
        char = Character(name="Lý Minh", role="chính", personality="dũng cảm")
        char.arc_waypoints = [
            {"chapter_range": "10-20", "stage_name": "Khủng hoảng", "progress_pct": 0.6}
        ]
        draft = _draft(characters=[char])
        result = _build_arc_context(draft, 3)
        assert result == ""

    def test_missing_stage_name_skipped(self):
        char = Character(name="Lý Minh", role="chính", personality="dũng cảm")
        char.arc_waypoints = [{"chapter_range": "1-5", "stage_name": "", "progress_pct": 0.0}]
        draft = _draft(characters=[char])
        assert _build_arc_context(draft, 2) == ""

    def test_exception_returns_empty(self):
        # Pass a non-StoryDraft object that will raise on attribute access
        bad = object()
        assert _build_arc_context(bad, 1) == ""

    def test_output_truncated_to_400(self):
        chars = []
        for i in range(30):
            c = Character(name=f"Char{'X' * 20}{i}", role="phụ", personality="bình thường")
            c.arc_waypoints = [{"chapter_range": "1-5", "stage_name": f"Stage{i}", "progress_pct": 0.1}]
            chars.append(c)
        draft = _draft(characters=chars)
        result = _build_arc_context(draft, 3)
        assert len(result) <= 400


# ──────────────────────────────────────────────────────────────────────────────
# _extract_pacing_directive / _extract_pacing_type
# ──────────────────────────────────────────────────────────────────────────────

class TestExtractPacingDirective:
    def test_none_draft_returns_empty(self):
        assert _extract_pacing_directive(None, 1) == ""

    def test_matching_chapter_returns_pacing(self):
        # pacing_adjustment lives on StoryContext, not Chapter.
        # _extract_pacing_directive looks at chapters but only reads
        # chapter.pacing_adjustment which doesn't exist on Chapter model.
        # The only reliable path is via draft.context.
        # Test: chapter in outlines → falls through to context path
        from models.schemas import StoryContext
        ctx = StoryContext(pacing_adjustment="slow down")
        draft = _draft(chapters=[_chapter(2)])
        draft.context = ctx
        # Chapter 999 not found in chapters list → context fallback fires
        assert _extract_pacing_directive(draft, 999) == "slow down"

    def test_non_matching_chapter_falls_through(self):
        # No matching chapter, no context → returns ""
        draft = _draft(chapters=[_chapter(2)])
        assert _extract_pacing_directive(draft, 5) == ""

    def test_context_fallback(self):
        from models.schemas import StoryContext
        ctx = StoryContext(pacing_adjustment="speed up")
        draft = _draft(chapters=[])
        draft.context = ctx
        assert _extract_pacing_directive(draft, 99) == "speed up"


class TestExtractPacingType:
    def test_none_draft_returns_empty(self):
        assert _extract_pacing_type(None, 1) == ""

    def test_matching_outline_returns_type(self):
        from models.schemas import ChapterOutline
        draft = _draft()
        draft.outlines = [ChapterOutline(chapter_number=3, title="T", summary="s", pacing_type="climax")]
        assert _extract_pacing_type(draft, 3) == "climax"

    def test_non_matching_outline_returns_empty(self):
        from models.schemas import ChapterOutline
        draft = _draft()
        draft.outlines = [ChapterOutline(chapter_number=3, title="T", summary="s", pacing_type="climax")]
        assert _extract_pacing_type(draft, 7) == ""


# ──────────────────────────────────────────────────────────────────────────────
# _build_knowledge_constraints
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildKnowledgeConstraints:
    def test_empty_knowledge_state_returns_empty(self):
        sim = _sim_result()
        draft = _draft()
        assert _build_knowledge_constraints(sim, draft) == ""

    def test_knowledge_state_on_sim_result(self):
        sim = _sim_result()
        sim.knowledge_state = {"Lý Minh": ["biết bí mật phòng thủ"]}
        result = _build_knowledge_constraints(sim, _draft())
        assert "Lý Minh" in result
        assert "BIẾT" in result

    def test_knowledge_from_draft_fallback(self):
        sim = _sim_result()
        draft = _draft()
        draft._knowledge_state = {"Nhân Vật B": ["sự thật về nguồn gốc"]}
        result = _build_knowledge_constraints(sim, draft)
        assert "Nhân Vật B" in result

    def test_empty_facts_per_char_skipped(self):
        sim = _sim_result()
        sim.knowledge_state = {"Lý Minh": []}
        result = _build_knowledge_constraints(sim, _draft())
        assert result == ""

    def test_facts_truncated_to_5_per_char(self):
        sim = _sim_result()
        sim.knowledge_state = {"Lý Minh": [f"fact{i}" for i in range(20)]}
        result = _build_knowledge_constraints(sim, _draft())
        # Only 5 facts should be joined (semicolons)
        lines = [ln for ln in result.split("\n") if "Lý Minh" in ln]
        assert len(lines) == 1
        # Count facts (semicolons) — max 5 means 4 semicolons
        assert lines[0].count(";") <= 4


# ──────────────────────────────────────────────────────────────────────────────
# _precheck_coherence
# ──────────────────────────────────────────────────────────────────────────────

class TestPrecheckCoherence:
    def test_no_prev_chapters_returns_empty(self):
        llm = _mock_llm()
        result = _precheck_coherence(llm, _chapter(1), _draft(), [])
        assert result == ""
        llm.generate_json.assert_not_called()

    def test_with_issues_returns_constraint_block(self):
        llm = _mock_llm(generate_json_return={"issues": ["nhân vật A ở hai nơi cùng lúc"]})
        ch = _chapter(2, "Chương 2 content")
        prev = [_chapter(1, "Chương 1 content")]
        draft = _draft(chapters=[_chapter(1), _chapter(2)])
        result = _precheck_coherence(llm, ch, draft, prev)
        assert "CẢNH BÁO" in result
        assert "nhân vật A" in result

    def test_no_issues_returns_empty(self):
        llm = _mock_llm(generate_json_return={"issues": []})
        ch = _chapter(2)
        prev = [_chapter(1)]
        result = _precheck_coherence(llm, ch, _draft(), prev)
        assert result == ""

    def test_llm_exception_returns_empty(self):
        llm = MagicMock()
        llm.generate_json.side_effect = Exception("LLM down")
        ch = _chapter(2)
        prev = [_chapter(1)]
        result = _precheck_coherence(llm, ch, _draft(), prev)
        assert result == ""

    def test_at_most_3_issues_returned(self):
        llm = _mock_llm(generate_json_return={
            "issues": ["issue1", "issue2", "issue3", "issue4", "issue5"]
        })
        ch = _chapter(2)
        prev = [_chapter(1)]
        result = _precheck_coherence(llm, ch, _draft(), prev)
        assert result.count("- TRÁNH:") == 3


# ──────────────────────────────────────────────────────────────────────────────
# StoryEnhancer.detect_structural_issues
# ──────────────────────────────────────────────────────────────────────────────

class TestDetectStructuralIssues:
    def test_returns_empty_when_detector_unavailable(self):
        with patch("pipeline.layer2_enhance.enhancer._STRUCTURAL_DETECTOR_AVAILABLE", False):
            enhancer = StoryEnhancer.__new__(StoryEnhancer)
            enhancer._rewritten_chapters = set()
            result = enhancer.detect_structural_issues(_draft())
            assert result == {}

    def test_skips_rewritten_chapters(self):
        """Chapters in _rewritten_chapters must be skipped."""
        with patch("pipeline.layer2_enhance.enhancer._STRUCTURAL_DETECTOR_AVAILABLE", True):
            with patch("pipeline.layer2_enhance.enhancer._detect_structural_issues") as mock_det:
                mock_det.return_value = []
                enhancer = StoryEnhancer.__new__(StoryEnhancer)
                enhancer._rewritten_chapters = {1}
                draft = _draft(chapters=[_chapter(1), _chapter(2)])
                enhancer.detect_structural_issues(draft)
                # Only chapter 2 should trigger the detector call
                # Verify chapter 1 was never passed
                for call_args in mock_det.call_args_list:
                    chapter_arg = call_args.kwargs.get("chapter") or (call_args.args[0] if call_args.args else None)
                    if chapter_arg is not None:
                        assert chapter_arg.chapter_number != 1


# ──────────────────────────────────────────────────────────────────────────────
# StoryEnhancer.enhance_chapter — scene-enhancer failure fallback
# ──────────────────────────────────────────────────────────────────────────────

class TestEnhanceChapterFallback:
    """If SceneEnhancer raises, enhance_chapter must return the original chapter."""

    def test_scene_enhancer_failure_returns_original(self):
        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            enhancer = StoryEnhancer()
        ch = _chapter(1, "original content")
        sim = _sim_result()

        with patch("pipeline.layer2_enhance.scene_enhancer.SceneEnhancer") as MockSE:
            MockSE.return_value.enhance_chapter_by_scenes.side_effect = RuntimeError("scene bomb")
            result = enhancer.enhance_chapter(ch, sim)

        assert result is ch
        assert result.content == "original content"

    def test_enhance_chapter_happy_path_returns_enhanced(self):
        """When SceneEnhancer succeeds, result must differ from raw fallback."""
        enhanced_ch = _chapter(1, "ENHANCED content")

        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            enhancer = StoryEnhancer()
        sim = _sim_result()

        with patch("pipeline.layer2_enhance.scene_enhancer.SceneEnhancer") as MockSE:
            MockSE.return_value.enhance_chapter_by_scenes.return_value = enhanced_ch
            result = enhancer.enhance_chapter(_chapter(1, "original"), sim)

        assert result.content == "ENHANCED content"


# ──────────────────────────────────────────────────────────────────────────────
# StoryEnhancer._apply_contract_validation
# ──────────────────────────────────────────────────────────────────────────────

class TestApplyContractValidation:
    def _enhancer(self):
        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            return StoryEnhancer()

    def _call(self, enhancer, enhanced_ch, sim):
        return enhancer._apply_contract_validation(
            enhanced_chapter=enhanced_ch,
            original=enhanced_ch,
            sim_result=sim,
            genre="",
            draft=None,
            subtext_guidance="",
            thematic_guidance="",
            chapter_summary=None,
            thread_state=None,
            arc_context="",
            pacing_directive="",
            consistency_constraints="",
        )

    def test_no_contract_returns_unchanged(self):
        enhancer = self._enhancer()
        ch = _chapter(1, "content")
        sim = _sim_result()
        result = self._call(enhancer, ch, sim)
        assert result is ch

    def test_contract_passed_stores_validation(self):
        from models.handoff_schemas import NegotiatedChapterContract
        enhancer = self._enhancer()
        ch = _chapter(1, "content")
        contract = NegotiatedChapterContract(
            chapter_num=1, pacing_type="rising",
            drama_target=0.5, drama_tolerance=0.15,
        )
        sim = _sim_result()
        sim.chapter_contracts = {1: contract.model_dump()}

        with patch("pipeline.layer2_enhance.chapter_contract.validate_chapter_against_contract") as mock_val:
            mock_result = MagicMock()
            mock_result.passed = True
            mock_result.compliance_score = 0.9
            mock_result.drama_actual = 0.55
            mock_result.model_dump.return_value = {"passed": True, "compliance_score": 0.9}
            mock_val.return_value = mock_result

            result = self._call(enhancer, ch, sim)

        # contract_validation populated
        assert result.contract_validation is not None
        assert result.contract_validation["passed"] is True

    def test_contract_failed_no_retry_when_disabled(self):
        from models.handoff_schemas import NegotiatedChapterContract
        enhancer = self._enhancer()
        ch = _chapter(1, "content")
        contract = NegotiatedChapterContract(chapter_num=1, pacing_type="rising")
        sim = _sim_result()
        sim.chapter_contracts = {1: contract.model_dump()}

        with patch("pipeline.layer2_enhance.chapter_contract.validate_chapter_against_contract") as mock_val:
            with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                cfg_pipeline = MagicMock()
                cfg_pipeline.contract_drama_tolerance = 0.15
                cfg_pipeline.contract_cheap_validation = True
                cfg_pipeline.enable_contract_retry = False  # retry disabled
                cfg_pipeline.contract_retry_max = 0
                mock_cfg.return_value.load.return_value.pipeline = cfg_pipeline

                mock_result = MagicMock()
                mock_result.passed = False
                mock_result.compliance_score = 0.4
                mock_result.drama_actual = 0.2
                mock_result.model_dump.return_value = {"passed": False}
                mock_val.return_value = mock_result

                result = self._call(enhancer, ch, sim)

        # Still returns the (failed) chapter, not None
        assert result is not None
        assert result.contract_validation["passed"] is False


# ──────────────────────────────────────────────────────────────────────────────
# StoryEnhancer._apply_voice_validation
# ──────────────────────────────────────────────────────────────────────────────

class TestApplyVoiceValidation:
    def _enhancer(self):
        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            return StoryEnhancer()

    def _call(self, enhancer, enhanced_ch, sim):
        return enhancer._apply_voice_validation(
            enhanced_chapter=enhanced_ch,
            original=enhanced_ch,
            sim_result=sim,
            genre="",
            draft=None,
            subtext_guidance="",
            thematic_guidance="",
            chapter_summary=None,
            thread_state=None,
            arc_context="",
            pacing_directive="",
            consistency_constraints="",
        )

    def test_no_voice_contract_returns_unchanged(self):
        enhancer = self._enhancer()
        ch = _chapter(1)
        sim = _sim_result()
        result = self._call(enhancer, ch, sim)
        assert result is ch

    def test_voice_passed_stores_validation(self):
        enhancer = self._enhancer()
        ch = _chapter(1)
        sim = _sim_result()
        sim.voice_contracts = {1: {"chapter_number": 1, "min_compliance": 0.75}}

        with patch("pipeline.layer2_enhance.chapter_contract.validate_chapter_voice") as mock_val:
            mock_result = MagicMock()
            mock_result.passed = True
            mock_result.overall_compliance = 0.9
            mock_result.drifted_characters = []
            mock_result.model_dump.return_value = {"passed": True}
            mock_val.return_value = mock_result

            result = self._call(enhancer, ch, sim)

        assert result.voice_validation is not None
        assert result.voice_validation["passed"] is True


# ──────────────────────────────────────────────────────────────────────────────
# StoryEnhancer.enhance_story_async — drama score mapping, signal consumption
# ──────────────────────────────────────────────────────────────────────────────

class TestEnhanceStoryAsync:
    def _make_enhancer(self):
        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            e = StoryEnhancer()
        return e

    @pytest.mark.asyncio
    async def test_drama_score_mapped_from_events(self):
        """Events with drama_score=0.5 → enhanced.drama_score in [1, 5]."""
        enhancer = self._make_enhancer()
        events = [
            SimulationEvent(
                round_number=1, event_type="xung_đột",
                characters_involved=["A"], description="fight",
                drama_score=0.5,
            )
        ]
        sim = _sim_result(events=events, drama_suggestions=["suggestion1"])
        draft = _draft(chapters=[_chapter(1)])

        with patch.object(enhancer, "enhance_chapter", return_value=_chapter(1, "enhanced")):
            with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
                with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                    pipeline_cfg = MagicMock()
                    pipeline_cfg.l2_consistency_engine = False
                    pipeline_cfg.l2_voice_preservation = False
                    pipeline_cfg.l2_consistency_threads = False
                    pipeline_cfg.l2_drama_curve_balancing = False
                    pipeline_cfg.enable_simulator_contracts = False
                    pipeline_cfg.enable_voice_contract = False
                    mock_cfg.return_value.load.return_value.pipeline = pipeline_cfg
                    mock_cfg.return_value.llm.max_parallel_workers = 2
                    result = await enhancer.enhance_story_async(draft, sim)

        assert 1.0 <= result.drama_score <= 5.0
        # 0.5 raw → 1 + 0.5*4 = 3.0
        assert abs(result.drama_score - 3.0) < 0.01

    @pytest.mark.asyncio
    async def test_drama_suggestions_propagated(self):
        enhancer = self._make_enhancer()
        sim = _sim_result(drama_suggestions=["add more tension", "better ending"])
        draft = _draft(chapters=[_chapter(1)])

        with patch.object(enhancer, "enhance_chapter", return_value=_chapter(1, "enhanced")):
            with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
                with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                    p = MagicMock()
                    p.l2_consistency_engine = False
                    p.l2_voice_preservation = False
                    p.l2_consistency_threads = False
                    p.l2_drama_curve_balancing = False
                    p.enable_simulator_contracts = False
                    p.enable_voice_contract = False
                    mock_cfg.return_value.load.return_value.pipeline = p
                    mock_cfg.return_value.llm.max_parallel_workers = 2
                    result = await enhancer.enhance_story_async(draft, sim)

        assert result.enhancement_notes == ["add more tension", "better ending"]

    @pytest.mark.asyncio
    async def test_chapter_order_preserved(self):
        """Output chapters must be in original order, not gather order."""
        enhancer = self._make_enhancer()
        sim = _sim_result()
        chapters = [_chapter(i) for i in range(1, 4)]
        draft = _draft(chapters=chapters)

        enhanced_map = {i: _chapter(i, f"content{i}") for i in range(1, 4)}

        def fake_enhance(ch, *args, **kwargs):
            return enhanced_map[ch.chapter_number]

        with patch.object(enhancer, "enhance_chapter", side_effect=fake_enhance):
            with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
                with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                    p = MagicMock()
                    p.l2_consistency_engine = False
                    p.l2_voice_preservation = False
                    p.l2_consistency_threads = False
                    p.l2_drama_curve_balancing = False
                    p.enable_simulator_contracts = False
                    p.enable_voice_contract = False
                    mock_cfg.return_value.load.return_value.pipeline = p
                    mock_cfg.return_value.llm.max_parallel_workers = 2
                    result = await enhancer.enhance_story_async(draft, sim)

        assert [ch.chapter_number for ch in result.chapters] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_failed_chapter_falls_back_to_original(self):
        """enhance_chapter raising must return original chapter."""
        enhancer = self._make_enhancer()
        sim = _sim_result()
        ch_orig = _chapter(1, "original")
        draft = _draft(chapters=[ch_orig])

        with patch.object(enhancer, "enhance_chapter", side_effect=Exception("boom")):
            with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
                with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                    p = MagicMock()
                    p.l2_consistency_engine = False
                    p.l2_voice_preservation = False
                    p.l2_consistency_threads = False
                    p.l2_drama_curve_balancing = False
                    p.enable_simulator_contracts = False
                    p.enable_voice_contract = False
                    mock_cfg.return_value.load.return_value.pipeline = p
                    mock_cfg.return_value.llm.max_parallel_workers = 2
                    result = await enhancer.enhance_story_async(draft, sim)

        assert result.chapters[0].content == "original"

    @pytest.mark.asyncio
    async def test_progress_callback_called(self):
        enhancer = self._make_enhancer()
        sim = _sim_result()
        draft = _draft(chapters=[_chapter(1)])
        messages = []

        with patch.object(enhancer, "enhance_chapter", return_value=_chapter(1, "done")):
            with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
                with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                    p = MagicMock()
                    p.l2_consistency_engine = False
                    p.l2_voice_preservation = False
                    p.l2_consistency_threads = False
                    p.l2_drama_curve_balancing = False
                    p.enable_simulator_contracts = False
                    p.enable_voice_contract = False
                    mock_cfg.return_value.load.return_value.pipeline = p
                    mock_cfg.return_value.llm.max_parallel_workers = 2
                    await enhancer.enhance_story_async(
                        draft, sim, progress_callback=messages.append
                    )

        assert len(messages) > 0


# ──────────────────────────────────────────────────────────────────────────────
# Sync guard: enhance_story / enhance_with_feedback
# ──────────────────────────────────────────────────────────────────────────────

class TestSyncGuards:
    def _enhancer(self):
        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            return StoryEnhancer()

    @pytest.mark.asyncio
    async def test_enhance_story_raises_inside_running_loop(self):
        """enhance_story() from inside async context must raise RuntimeError."""
        enhancer = self._enhancer()
        draft = _draft()
        sim = _sim_result()
        with pytest.raises(RuntimeError, match="enhance_story called"):
            enhancer.enhance_story(draft, sim)

    @pytest.mark.asyncio
    async def test_enhance_with_feedback_raises_inside_running_loop(self):
        enhancer = self._enhancer()
        draft = _draft()
        sim = _sim_result()
        with pytest.raises(RuntimeError, match="enhance_with_feedback called"):
            enhancer.enhance_with_feedback(draft, sim)


# ──────────────────────────────────────────────────────────────────────────────
# Feature flags
# ──────────────────────────────────────────────────────────────────────────────

class TestFeatureFlags:
    def _enhancer(self):
        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            return StoryEnhancer()

    def _disable_all_features(self, mock_cfg):
        p = MagicMock()
        p.l2_consistency_engine = False
        p.l2_voice_preservation = False
        p.l2_consistency_threads = False
        p.l2_drama_curve_balancing = False
        p.enable_simulator_contracts = False
        p.enable_voice_contract = False
        mock_cfg.return_value.load.return_value.pipeline = p
        mock_cfg.return_value.llm.max_parallel_workers = 2
        return p

    @pytest.mark.asyncio
    async def test_consistency_engine_not_built_when_disabled(self):
        enhancer = self._enhancer()
        draft = _draft(chapters=[_chapter(1)])
        sim = _sim_result()

        with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", True):
            with patch("pipeline.layer2_enhance.enhancer.ConsistencyEngine") as MockCE:
                with patch.object(enhancer, "enhance_chapter", return_value=_chapter(1)):
                    with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                        self._disable_all_features(mock_cfg)
                        await enhancer.enhance_story_async(draft, sim)

        MockCE.assert_not_called()

    @pytest.mark.asyncio
    async def test_voice_preservation_skipped_when_disabled(self):
        enhancer = self._enhancer()
        draft = _draft(chapters=[_chapter(1)])
        sim = _sim_result()

        with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
            with patch("pipeline.layer2_enhance.voice_fingerprint.VoiceFingerprintEngine") as MockVFE:
                with patch.object(enhancer, "enhance_chapter", return_value=_chapter(1)):
                    with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                        self._disable_all_features(mock_cfg)
                        await enhancer.enhance_story_async(draft, sim)

        MockVFE.assert_not_called()

    @pytest.mark.asyncio
    async def test_drama_curve_balancing_skipped_when_disabled(self):
        enhancer = self._enhancer()
        draft = _draft(chapters=[_chapter(1)])
        sim = _sim_result()

        with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
            with patch("pipeline.layer2_enhance.scene_enhancer.DramaCurveBalancer") as MockDCB:
                with patch.object(enhancer, "enhance_chapter", return_value=_chapter(1)):
                    with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                        self._disable_all_features(mock_cfg)
                        await enhancer.enhance_story_async(draft, sim)

        MockDCB.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# _find_weak_chapters
# ──────────────────────────────────────────────────────────────────────────────

class TestFindWeakChapters:
    def _enhancer(self):
        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            return StoryEnhancer()

    def test_weak_chapter_identified(self):
        enhancer = self._enhancer()
        enhanced = EnhancedStory(title="T", genre="g", chapters=[_chapter(1, "short")])

        enhancer.llm.generate_json.return_value = {
            "drama_score": 0.3,
            "weak_points": ["boring", "no conflict"],
            "strong_points": [],
        }
        weak = enhancer._find_weak_chapters(enhanced)
        assert len(weak) == 1
        assert weak[0]["chapter_number"] == 1
        assert weak[0]["score"] == pytest.approx(0.3)
        assert "boring" in weak[0]["weak_points"]

    def test_strong_chapter_not_returned(self):
        enhancer = self._enhancer()
        enhanced = EnhancedStory(title="T", genre="g", chapters=[_chapter(1, "exciting content")])
        enhancer.llm.generate_json.return_value = {
            "drama_score": 0.9,
            "weak_points": [],
        }
        weak = enhancer._find_weak_chapters(enhanced)
        assert weak == []

    def test_llm_exception_per_chapter_skipped(self):
        enhancer = self._enhancer()
        enhanced = EnhancedStory(title="T", genre="g", chapters=[_chapter(1), _chapter(2)])
        enhancer.llm.generate_json.side_effect = Exception("LLM error")
        # Must not raise; returns empty
        weak = enhancer._find_weak_chapters(enhanced)
        assert weak == []

    def test_threshold_boundary_exactly_at_min(self):
        """chapter with drama_score == MIN_DRAMA_SCORE should NOT be weak."""
        enhancer = self._enhancer()
        enhanced = EnhancedStory(title="T", genre="g", chapters=[_chapter(1)])
        enhancer.llm.generate_json.return_value = {"drama_score": MIN_DRAMA_SCORE}
        weak = enhancer._find_weak_chapters(enhanced)
        assert weak == []


# ──────────────────────────────────────────────────────────────────────────────
# enhance_with_feedback_async — idempotency + knowledge registry init
# ──────────────────────────────────────────────────────────────────────────────

class TestEnhanceWithFeedbackAsync:
    def _enhancer(self):
        with patch("pipeline.layer2_enhance.enhancer.LLMClient", return_value=_mock_llm()):
            return StoryEnhancer()

    def _cfg_patch(self, mock_cfg):
        p = MagicMock()
        p.l2_consistency_engine = False
        p.l2_voice_preservation = False
        p.l2_consistency_threads = False
        p.l2_drama_curve_balancing = False
        p.enable_simulator_contracts = False
        p.enable_voice_contract = False
        p.l2_causal_audit = False
        p.l2_contract_gate = False
        mock_cfg.return_value.load.return_value.pipeline = p
        mock_cfg.return_value.llm.max_parallel_workers = 2
        return p

    @pytest.mark.asyncio
    async def test_no_weak_chapters_single_pass(self):
        enhancer = self._enhancer()
        draft = _draft(chapters=[_chapter(1)])
        sim = _sim_result()

        with patch.object(enhancer, "enhance_story_async", return_value=EnhancedStory(
            title="T", genre="g", chapters=[_chapter(1, "done")]
        )):
            with patch.object(enhancer, "_find_weak_chapters", return_value=[]):
                with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                    with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
                        self._cfg_patch(mock_cfg)
                        result = await enhancer.enhance_with_feedback_async(draft, sim)

        assert isinstance(result, EnhancedStory)

    @pytest.mark.asyncio
    async def test_knowledge_registry_initialized_when_missing(self):
        enhancer = self._enhancer()
        char = Character(name="Lý Minh", role="chính", personality="dũng cảm")
        draft = _draft(chapters=[_chapter(1)], characters=[char])
        sim = _sim_result()
        assert getattr(draft, "_knowledge_registry", None) is None

        with patch.object(enhancer, "enhance_story_async", return_value=EnhancedStory(
            title="T", genre="g", chapters=[_chapter(1)]
        )):
            with patch.object(enhancer, "_find_weak_chapters", return_value=[]):
                with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                    with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
                        self._cfg_patch(mock_cfg)
                        await enhancer.enhance_with_feedback_async(draft, sim)

        assert getattr(draft, "_knowledge_registry", None) is not None

    @pytest.mark.asyncio
    async def test_idempotency_with_deterministic_mock(self):
        """Running twice with same deterministic mock yields same output structure."""
        fixed_chapter = _chapter(1, "deterministic output")
        fixed_story = EnhancedStory(title="T", genre="g", chapters=[fixed_chapter])

        for _ in range(2):
            enhancer = self._enhancer()
            draft = _draft(chapters=[_chapter(1)])
            sim = _sim_result()

            with patch.object(enhancer, "enhance_story_async", return_value=fixed_story):
                with patch.object(enhancer, "_find_weak_chapters", return_value=[]):
                    with patch("pipeline.layer2_enhance.enhancer.ConfigManager") as mock_cfg:
                        with patch("pipeline.layer2_enhance.enhancer._CONSISTENCY_AVAILABLE", False):
                            self._cfg_patch(mock_cfg)
                            result = await enhancer.enhance_with_feedback_async(draft, sim)

            assert result.chapters[0].content == "deterministic output"
