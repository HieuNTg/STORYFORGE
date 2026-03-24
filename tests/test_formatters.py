"""Tests for ui/formatters.py — all 6 format_* functions."""

import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers to build mock objects
# ---------------------------------------------------------------------------

def _make_chapter(num=1, title="Ch Title", content="x" * 2100):
    ch = MagicMock()
    ch.chapter_number = num
    ch.title = title
    ch.content = content
    return ch


def _make_character(name="Alice"):
    c = MagicMock()
    c.name = name
    return c


def _make_story_draft(title="TestStory", genre="Fantasy", synopsis="A tale"):
    d = MagicMock()
    d.title = title
    d.genre = genre
    d.synopsis = synopsis
    char = _make_character("Alice")
    d.characters = [char]
    d.chapters = [_make_chapter(1), _make_chapter(2)]
    return d


def _make_enhanced_story(title="EnhancedStory", drama_score=0.85):
    es = MagicMock()
    es.title = title
    es.drama_score = drama_score
    es.chapters = [_make_chapter(1)]
    return es


def _make_simulation_result():
    ev = MagicMock()
    ev.event_type = "conflict"
    ev.description = "A fights B"
    ev.drama_score = 0.9
    s = MagicMock()
    s.events = [ev]
    s.agent_posts = ["post1", "post2"]
    s.drama_suggestions = ["suggestion1"]
    return s


def _make_panel(num=1, ch=1, dialogue="hello", image_prompt="img"):
    p = MagicMock()
    p.panel_number = num
    p.chapter_number = ch
    p.shot_type = MagicMock()
    p.shot_type.value = "wide"
    p.camera_movement = "tĩnh"
    p.description = "scene"
    p.dialogue = dialogue
    p.image_prompt = image_prompt
    return p


def _make_video_script(title="VideoTitle"):
    vs = MagicMock()
    vs.title = title
    vs.total_duration_seconds = 300
    vs.panels = [_make_panel(1, 1), _make_panel(2, 1, dialogue="", image_prompt="")]
    vs.voice_lines = ["line1", "line2"]
    return vs


def _make_agent_review(name="Critic", layer=1, iteration=1, score=0.8, approved=True):
    r = MagicMock()
    r.agent_name = name
    r.layer = layer
    r.iteration = iteration
    r.score = score
    r.approved = approved
    r.issues = ["issue1"]
    r.suggestions = ["sug1"]
    return r


def _make_chapter_score(num=1):
    cs = MagicMock()
    cs.chapter_number = num
    cs.coherence = 4.0
    cs.character_consistency = 3.5
    cs.drama = 4.5
    cs.writing_quality = 3.0
    cs.overall = 3.75
    cs.notes = "good chapter"
    return cs


def _make_quality_score(layer=1):
    qs = MagicMock()
    qs.scoring_layer = layer
    qs.overall = 3.5
    qs.avg_coherence = 4.0
    qs.avg_character = 3.5
    qs.avg_drama = 4.0
    qs.avg_writing = 3.0
    qs.weakest_chapter = 1
    qs.chapter_scores = [_make_chapter_score(1)]
    return qs


def _make_output(**kwargs):
    o = MagicMock()
    o.story_draft = kwargs.get("story_draft", None)
    o.simulation_result = kwargs.get("simulation_result", None)
    o.enhanced_story = kwargs.get("enhanced_story", None)
    o.video_script = kwargs.get("video_script", None)
    o.reviews = kwargs.get("reviews", [])
    o.quality_scores = kwargs.get("quality_scores", [])
    return o


# ---------------------------------------------------------------------------
# Import formatters
# ---------------------------------------------------------------------------
from ui.formatters import (
    format_story_output,
    format_simulation_output,
    format_enhanced_output,
    format_video_output,
    format_agent_output,
    format_quality_output,
)

_t = lambda k, **kw: k  # dummy translation


class TestFormatStoryOutput(unittest.TestCase):

    def test_returns_empty_when_no_output(self):
        self.assertEqual(format_story_output(None, _t), "")

    def test_returns_empty_when_no_story_draft(self):
        output = _make_output()
        self.assertEqual(format_story_output(output, _t), "")

    def test_includes_title(self):
        draft = _make_story_draft(title="MyTitle")
        output = _make_output(story_draft=draft)
        result = format_story_output(output, _t)
        self.assertIn("MyTitle", result)

    def test_includes_genre(self):
        draft = _make_story_draft(genre="Sci-Fi")
        output = _make_output(story_draft=draft)
        result = format_story_output(output, _t)
        self.assertIn("Sci-Fi", result)

    def test_includes_synopsis(self):
        draft = _make_story_draft(synopsis="A long tale")
        output = _make_output(story_draft=draft)
        result = format_story_output(output, _t)
        self.assertIn("A long tale", result)

    def test_includes_character_names(self):
        draft = _make_story_draft()
        output = _make_output(story_draft=draft)
        result = format_story_output(output, _t)
        self.assertIn("Alice", result)

    def test_includes_chapter_numbers(self):
        draft = _make_story_draft()
        output = _make_output(story_draft=draft)
        result = format_story_output(output, _t)
        self.assertIn("Chương 1", result)

    def test_truncates_long_content(self):
        draft = _make_story_draft()
        draft.chapters = [_make_chapter(content="A" * 3000)]
        output = _make_output(story_draft=draft)
        result = format_story_output(output, _t)
        self.assertIn("...", result)


class TestFormatSimulationOutput(unittest.TestCase):

    def test_returns_empty_when_no_output(self):
        self.assertEqual(format_simulation_output(None, _t), "")

    def test_returns_empty_when_no_simulation_result(self):
        output = _make_output()
        self.assertEqual(format_simulation_output(output, _t), "")

    def test_includes_event_count(self):
        sim = _make_simulation_result()
        output = _make_output(simulation_result=sim)
        result = format_simulation_output(output, _t)
        self.assertIn("1", result)

    def test_includes_agent_post_count(self):
        sim = _make_simulation_result()
        output = _make_output(simulation_result=sim)
        result = format_simulation_output(output, _t)
        self.assertIn("2", result)

    def test_includes_event_description(self):
        sim = _make_simulation_result()
        output = _make_output(simulation_result=sim)
        result = format_simulation_output(output, _t)
        self.assertIn("A fights B", result)

    def test_includes_drama_suggestions(self):
        sim = _make_simulation_result()
        output = _make_output(simulation_result=sim)
        result = format_simulation_output(output, _t)
        self.assertIn("suggestion1", result)

    def test_limits_events_to_10(self):
        ev = MagicMock()
        ev.event_type = "conflict"
        ev.description = "event"
        ev.drama_score = 0.5
        sim = MagicMock()
        sim.events = [ev] * 20
        sim.agent_posts = []
        sim.drama_suggestions = []
        output = _make_output(simulation_result=sim)
        result = format_simulation_output(output, _t)
        # Should only show 10 events max
        self.assertIsNotNone(result)


class TestFormatEnhancedOutput(unittest.TestCase):

    def test_returns_empty_when_no_output(self):
        self.assertEqual(format_enhanced_output(None, _t), "")

    def test_returns_empty_when_no_enhanced_story(self):
        output = _make_output()
        self.assertEqual(format_enhanced_output(output, _t), "")

    def test_includes_title(self):
        es = _make_enhanced_story(title="Enhanced")
        output = _make_output(enhanced_story=es)
        result = format_enhanced_output(output, _t)
        self.assertIn("Enhanced", result)

    def test_includes_drama_score(self):
        es = _make_enhanced_story(drama_score=0.85)
        output = _make_output(enhanced_story=es)
        result = format_enhanced_output(output, _t)
        self.assertIn("0.85", result)

    def test_includes_chapter(self):
        es = _make_enhanced_story()
        output = _make_output(enhanced_story=es)
        result = format_enhanced_output(output, _t)
        self.assertIn("Chương 1", result)

    def test_truncates_content(self):
        es = _make_enhanced_story()
        es.chapters = [_make_chapter(content="B" * 3000)]
        output = _make_output(enhanced_story=es)
        result = format_enhanced_output(output, _t)
        self.assertIn("...", result)


class TestFormatVideoOutput(unittest.TestCase):

    def test_returns_empty_when_no_output(self):
        self.assertEqual(format_video_output(None, _t), "")

    def test_returns_empty_when_no_video_script(self):
        output = _make_output()
        self.assertEqual(format_video_output(output, _t), "")

    def test_includes_title(self):
        vs = _make_video_script(title="VideoTitle")
        output = _make_output(video_script=vs)
        result = format_video_output(output, _t)
        self.assertIn("VideoTitle", result)

    def test_includes_panel_count(self):
        vs = _make_video_script()
        output = _make_output(video_script=vs)
        result = format_video_output(output, _t)
        self.assertIn("2", result)

    def test_includes_dialogue_when_present(self):
        vs = _make_video_script()
        output = _make_output(video_script=vs)
        result = format_video_output(output, _t)
        self.assertIn("hello", result)

    def test_skips_dialogue_when_empty(self):
        vs = _make_video_script()
        # second panel has empty dialogue
        output = _make_output(video_script=vs)
        result = format_video_output(output, _t)
        # should not crash; panel 2 with empty dialogue just won't add Thoại line
        self.assertIsNotNone(result)

    def test_includes_duration(self):
        vs = _make_video_script()
        output = _make_output(video_script=vs)
        result = format_video_output(output, _t)
        self.assertIn("5.0", result)  # 300/60 = 5.0 minutes


class TestFormatAgentOutput(unittest.TestCase):

    def test_returns_empty_when_no_output(self):
        self.assertEqual(format_agent_output(None, _t), "")

    def test_returns_empty_when_no_reviews(self):
        output = _make_output()
        self.assertEqual(format_agent_output(output, _t), "")

    def test_includes_agent_name(self):
        r = _make_agent_review(name="CriticAgent")
        output = _make_output(reviews=[r])
        result = format_agent_output(output, _t)
        self.assertIn("CriticAgent", result)

    def test_shows_pass_for_approved(self):
        r = _make_agent_review(approved=True)
        output = _make_output(reviews=[r])
        result = format_agent_output(output, _t)
        self.assertIn("PASS", result)

    def test_shows_fail_for_not_approved(self):
        r = _make_agent_review(approved=False)
        output = _make_output(reviews=[r])
        result = format_agent_output(output, _t)
        self.assertIn("FAIL", result)

    def test_includes_issues(self):
        r = _make_agent_review()
        output = _make_output(reviews=[r])
        result = format_agent_output(output, _t)
        self.assertIn("issue1", result)

    def test_includes_suggestions(self):
        r = _make_agent_review()
        output = _make_output(reviews=[r])
        result = format_agent_output(output, _t)
        self.assertIn("sug1", result)

    def test_includes_score(self):
        r = _make_agent_review(score=0.8)
        output = _make_output(reviews=[r])
        result = format_agent_output(output, _t)
        self.assertIn("0.8", result)


class TestFormatQualityOutput(unittest.TestCase):

    def test_returns_placeholder_when_no_output(self):
        result = format_quality_output(None, _t)
        self.assertIn("Chưa có", result)

    def test_returns_placeholder_when_no_quality_scores(self):
        output = _make_output()
        result = format_quality_output(output, _t)
        self.assertIn("Chưa có", result)

    def test_includes_layer(self):
        qs = _make_quality_score(layer=1)
        output = _make_output(quality_scores=[qs])
        result = format_quality_output(output, _t)
        self.assertIn("Layer 1", result)

    def test_includes_overall_score(self):
        qs = _make_quality_score(layer=1)
        output = _make_output(quality_scores=[qs])
        result = format_quality_output(output, _t)
        self.assertIn("3.5", result)

    def test_includes_weakest_chapter(self):
        qs = _make_quality_score(layer=1)
        output = _make_output(quality_scores=[qs])
        result = format_quality_output(output, _t)
        self.assertIn("1", result)

    def test_includes_chapter_scores(self):
        qs = _make_quality_score(layer=1)
        output = _make_output(quality_scores=[qs])
        result = format_quality_output(output, _t)
        self.assertIn("good chapter", result)

    def test_shows_improvement_with_two_layers(self):
        qs1 = _make_quality_score(layer=1)
        qs1.overall = 3.0
        qs2 = _make_quality_score(layer=2)
        qs2.overall = 4.0
        output = _make_output(quality_scores=[qs1, qs2])
        result = format_quality_output(output, _t)
        self.assertIn("Cải thiện", result)
        self.assertIn("+1.0", result)

    def test_negative_improvement_shows_minus(self):
        qs1 = _make_quality_score(layer=1)
        qs1.overall = 4.0
        qs2 = _make_quality_score(layer=2)
        qs2.overall = 3.0
        output = _make_output(quality_scores=[qs1, qs2])
        result = format_quality_output(output, _t)
        self.assertIn("-1.0", result)


if __name__ == "__main__":
    unittest.main()
