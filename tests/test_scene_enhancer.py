"""Tests for SceneEnhancer and DramaCurveBalancer (Phase 7 improvements)."""

from unittest.mock import MagicMock, patch

from pipeline.layer2_enhance.scene_enhancer import (
    DramaCurveTarget,
    DramaCurveBalancer,
    SceneEnhancer,
    SceneScore,
)
from models.schemas import Chapter, SimulationResult


def _make_chapter(num: int, content: str = "") -> Chapter:
    return Chapter(
        chapter_number=num,
        title=f"Chapter {num}",
        content=content or f"Content of chapter {num} " * 50,
        word_count=200,
    )


def _make_sim_result() -> SimulationResult:
    return SimulationResult(events=[], insights="")


class TestDramaCurveTarget:
    """Tests for DramaCurveTarget.get_target_score()."""

    def test_single_chapter_returns_default(self):
        score = DramaCurveTarget.get_target_score(1, 1, DramaCurveTarget.RISING)
        assert score == 0.7

    def test_rising_curve_increases(self):
        scores = [
            DramaCurveTarget.get_target_score(ch, 10, DramaCurveTarget.RISING)
            for ch in range(1, 11)
        ]
        # Each score should be >= previous
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i - 1]
        # First should be around 0.4, last around 0.9
        assert 0.3 < scores[0] < 0.5
        assert 0.85 < scores[-1] <= 0.95

    def test_climax_at_end_curve(self):
        scores = [
            DramaCurveTarget.get_target_score(ch, 10, DramaCurveTarget.CLIMAX_AT_END)
            for ch in range(1, 11)
        ]
        # Last 3 chapters should rise sharply
        assert scores[9] > scores[6]
        # Early chapters should be moderate
        assert scores[2] < 0.65

    def test_wave_curve_has_peaks(self):
        scores = [
            DramaCurveTarget.get_target_score(ch, 100, DramaCurveTarget.WAVE)
            for ch in range(1, 101)
        ]
        # Should have peaks and valleys (variance > 0)
        variance = sum((s - sum(scores) / len(scores)) ** 2 for s in scores) / len(scores)
        assert variance > 0.01  # Has meaningful variation

    def test_unknown_curve_returns_default(self):
        score = DramaCurveTarget.get_target_score(5, 10, "unknown_curve")
        assert score == 0.6


class TestDramaCurveBalancer:
    """Tests for DramaCurveBalancer class."""

    def test_init_defaults(self):
        balancer = DramaCurveBalancer()
        assert balancer.curve_type == "rising"
        assert balancer.chapter_scores == {}

    def test_set_scores_computes_targets(self):
        balancer = DramaCurveBalancer(curve_type="rising")
        balancer.set_scores({1: 0.5, 2: 0.6, 3: 0.7}, total_chapters=3)

        assert len(balancer.target_scores) == 3
        assert 1 in balancer.target_scores
        assert 2 in balancer.target_scores
        assert 3 in balancer.target_scores

    def test_adjustment_for_low_drama_chapter(self):
        balancer = DramaCurveBalancer(curve_type="rising")
        # Chapter 10 of 10 should need high drama (~0.9), give it 0.3
        balancer.set_scores({10: 0.3}, total_chapters=10)

        delta, directive = balancer.get_chapter_adjustment(10)
        assert delta > 0.3  # Needs significant boost
        assert directive == "escalate"

    def test_adjustment_for_high_drama_chapter(self):
        balancer = DramaCurveBalancer(curve_type="rising")
        # Chapter 1 of 10 should need low drama (~0.45), give it 0.9
        balancer.set_scores({1: 0.9}, total_chapters=10)

        delta, directive = balancer.get_chapter_adjustment(1)
        assert delta < -0.15  # Needs toning down
        assert directive == "tone_down"

    def test_no_adjustment_for_matching_chapter(self):
        balancer = DramaCurveBalancer(curve_type="rising")
        # Chapter 5 of 10 should need ~0.65, give it 0.65
        balancer.set_scores({5: 0.65}, total_chapters=10)

        delta, directive = balancer.get_chapter_adjustment(5)
        assert abs(delta) < 0.16  # Within tolerance
        assert directive == ""

    def test_get_min_drama_for_chapter(self):
        balancer = DramaCurveBalancer(curve_type="rising")
        balancer.set_scores({}, total_chapters=10)

        # Late chapter should have higher min
        min_late = balancer.get_min_drama_for_chapter(10, base_min=0.6)
        min_early = balancer.get_min_drama_for_chapter(1, base_min=0.6)
        assert min_late > min_early

    def test_get_summary(self):
        balancer = DramaCurveBalancer(curve_type="rising")
        # Not initialized
        summary = balancer.get_summary()
        assert summary["status"] == "not_initialized"

        # After setting scores
        balancer.set_scores({1: 0.3, 2: 0.5, 3: 0.7, 4: 0.9, 5: 0.4}, total_chapters=5)
        summary = balancer.get_summary()

        assert "curve_type" in summary
        assert summary["curve_type"] == "rising"
        assert "avg_actual" in summary
        assert "chapters_need_boost" in summary
        assert "chapters_need_reduction" in summary


class TestSceneEnhancerConfig:
    """Tests for SceneEnhancer config loading."""

    def test_defaults_are_set(self):
        # SceneEnhancer should always have these attributes
        enhancer = SceneEnhancer()

        assert hasattr(enhancer, "parallel_enabled")
        assert hasattr(enhancer, "retry_max")
        assert hasattr(enhancer, "retry_threshold")
        # Defaults when config works or fails
        assert isinstance(enhancer.parallel_enabled, bool)
        assert isinstance(enhancer.retry_max, int)
        assert isinstance(enhancer.retry_threshold, float)

    def test_can_override_config_after_init(self):
        enhancer = SceneEnhancer()
        enhancer.parallel_enabled = False
        enhancer.retry_max = 5
        enhancer.retry_threshold = 0.7

        assert enhancer.parallel_enabled is False
        assert enhancer.retry_max == 5
        assert enhancer.retry_threshold == 0.7


class TestSceneEnhancerRouting:
    """Tests for parallel/sequential routing in enhance_weak_scenes."""

    def test_sequential_when_parallel_disabled(self):
        enhancer = SceneEnhancer()
        enhancer.parallel_enabled = False
        enhancer.retry_max = 0
        enhancer.llm = MagicMock()
        enhancer.llm.generate.return_value = "Enhanced content"

        chapter = _make_chapter(1)
        scenes = [{"scene_number": 1, "content": "weak scene"}]
        scores = [SceneScore(scene_number=1, drama_score=0.3, needs_enhancement=True)]

        with patch.object(enhancer, "_enhance_scenes_sequential") as mock_seq:
            mock_seq.return_value = {1: "Enhanced content"}
            enhancer.enhance_weak_scenes(
                chapter, scenes, scores, _make_sim_result(), "drama"
            )
            mock_seq.assert_called_once()

    def test_sequential_when_single_weak_scene(self):
        enhancer = SceneEnhancer()
        enhancer.parallel_enabled = True  # Parallel enabled
        enhancer.retry_max = 0
        enhancer.llm = MagicMock()

        chapter = _make_chapter(1)
        scenes = [{"scene_number": 1, "content": "weak scene"}]
        scores = [SceneScore(scene_number=1, drama_score=0.3, needs_enhancement=True)]

        with patch.object(enhancer, "_enhance_scenes_sequential") as mock_seq:
            mock_seq.return_value = {1: "Enhanced content"}
            # Only 1 weak scene, should use sequential even with parallel enabled
            enhancer.enhance_weak_scenes(
                chapter, scenes, scores, _make_sim_result(), "drama"
            )
            mock_seq.assert_called_once()

    def test_parallel_when_multiple_weak_scenes(self):
        enhancer = SceneEnhancer()
        enhancer.parallel_enabled = True
        enhancer.retry_max = 0
        enhancer.llm = MagicMock()

        chapter = _make_chapter(1)
        scenes = [
            {"scene_number": 1, "content": "weak scene 1"},
            {"scene_number": 2, "content": "weak scene 2"},
        ]
        scores = [
            SceneScore(scene_number=1, drama_score=0.3, needs_enhancement=True),
            SceneScore(scene_number=2, drama_score=0.4, needs_enhancement=True),
        ]

        with patch.object(enhancer, "_enhance_scenes_parallel") as mock_par:
            mock_par.return_value = {1: "Enhanced 1", 2: "Enhanced 2"}
            # 2 weak scenes with parallel enabled, should use parallel
            enhancer.enhance_weak_scenes(
                chapter, scenes, scores, _make_sim_result(), "drama"
            )
            mock_par.assert_called_once()


class TestSceneEnhancerRetry:
    """Tests for retry logic in _enhance_single_scene_with_retry."""

    def test_returns_early_if_score_meets_threshold(self):
        enhancer = SceneEnhancer()
        enhancer.retry_max = 2
        enhancer.retry_threshold = 0.5
        enhancer.llm = MagicMock()
        enhancer.llm.generate.return_value = "Enhanced content"
        enhancer.llm.generate_json.return_value = {"drama_score": 0.7, "weak_points": []}

        scene = {"scene_number": 1, "content": "weak"}
        score = SceneScore(scene_number=1, drama_score=0.3, weak_points=["boring"])
        context = {
            "genre": "drama",
            "events": "",
            "subtext_guidance": "",
            "thematic_guidance": "",
            "preserve_facts": "",
            "thread_status": "",
            "arc_context": "",
            "consistency_constraints": "",
            "curve_directive": "",
        }

        result = enhancer._enhance_single_scene_with_retry(scene, score, context)

        # Should return after first success (score 0.7 > threshold 0.5)
        assert result == "Enhanced content"
        assert enhancer.llm.generate.call_count == 1

    def test_retries_when_score_below_threshold(self):
        enhancer = SceneEnhancer()
        enhancer.retry_max = 2
        enhancer.retry_threshold = 0.6
        enhancer.llm = MagicMock()
        enhancer.llm.generate.return_value = "Enhanced content"
        # First two rescores fail, third passes
        enhancer.llm.generate_json.side_effect = [
            {"drama_score": 0.4, "weak_points": ["still weak"]},
            {"drama_score": 0.5, "weak_points": ["almost"]},
        ]

        scene = {"scene_number": 1, "content": "weak"}
        score = SceneScore(scene_number=1, drama_score=0.3, weak_points=["boring"])
        context = {
            "genre": "drama",
            "events": "",
            "subtext_guidance": "",
            "thematic_guidance": "",
            "preserve_facts": "",
            "thread_status": "",
            "arc_context": "",
            "consistency_constraints": "",
            "curve_directive": "",
        }

        enhancer._enhance_single_scene_with_retry(scene, score, context)

        # Should retry up to retry_max times
        assert enhancer.llm.generate.call_count == 3  # initial + 2 retries


class TestCurveDirectiveInjection:
    """Tests for curve directive injection into weak_points."""

    def test_escalate_directive_added(self):
        enhancer = SceneEnhancer()
        enhancer.retry_max = 0
        enhancer.llm = MagicMock()
        enhancer.llm.generate.return_value = "Enhanced"

        scene = {"scene_number": 1, "content": "weak"}
        score = SceneScore(scene_number=1, drama_score=0.3, weak_points=["boring"])
        context = {
            "genre": "drama",
            "events": "",
            "subtext_guidance": "",
            "thematic_guidance": "",
            "preserve_facts": "",
            "thread_status": "",
            "arc_context": "",
            "consistency_constraints": "",
            "curve_directive": "escalate",
        }

        enhancer._enhance_single_scene_with_retry(scene, score, context)

        # Check that "escalate" directive was included in the prompt
        call_args = enhancer.llm.generate.call_args
        prompt = call_args[1]["user_prompt"]
        assert "TĂNG KỊCH TÍNH" in prompt

    def test_tone_down_directive_added(self):
        enhancer = SceneEnhancer()
        enhancer.retry_max = 0
        enhancer.llm = MagicMock()
        enhancer.llm.generate.return_value = "Enhanced"

        scene = {"scene_number": 1, "content": "weak"}
        score = SceneScore(scene_number=1, drama_score=0.3, weak_points=["boring"])
        context = {
            "genre": "drama",
            "events": "",
            "subtext_guidance": "",
            "thematic_guidance": "",
            "preserve_facts": "",
            "thread_status": "",
            "arc_context": "",
            "consistency_constraints": "",
            "curve_directive": "tone_down",
        }

        enhancer._enhance_single_scene_with_retry(scene, score, context)

        call_args = enhancer.llm.generate.call_args
        prompt = call_args[1]["user_prompt"]
        assert "GIẢM NHẸ KỊCH TÍNH" in prompt
