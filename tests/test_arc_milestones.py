"""Sprint 3 Task 3 — Cross-chapter ArcMilestone contract.

Covers:
- ArcMilestone schema defaults
- generate_arc_milestones validates arc_bound clamping + malformed entries
- check_milestones_in_chapter keyword heuristic (match threshold)
- audit_arc_milestones marks overdue pendings as missed + aggregates drift
- format_milestone_warnings produces user-facing strings
- Config flag enable_arc_milestones defaults false
- StoryDraft has arc_milestones + arc_milestone_audit fields
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from models.schemas import ArcMilestone, Chapter, MacroArc, StoryDraft
from pipeline.layer1_story.arc_milestone_manager import (
    audit_arc_milestones,
    check_milestones_in_chapter,
    format_milestone_warnings,
    generate_arc_milestones,
)


def _arc(num=1, start=1, end=5):
    return MacroArc(
        arc_number=num, name=f"Arc{num}",
        chapter_start=start, chapter_end=end,
        central_conflict="power", character_focus=["Linh"],
    )


def _milestone(mid="m1_a1", arc=1, chapter=3, keywords=("thất bại", "sụp đổ")):
    return ArcMilestone(
        milestone_id=mid, arc_number=arc, description="First defeat",
        required_by_chapter=chapter, keywords=list(keywords),
        characters_involved=["Linh"],
    )


def _chapter(num, content):
    return Chapter(chapter_number=num, title=f"Ch{num}", content=content)


class TestArcMilestoneSchema(unittest.TestCase):
    def test_defaults(self):
        m = ArcMilestone(
            milestone_id="x", arc_number=1, description="d",
            required_by_chapter=1,
        )
        self.assertEqual(m.status, "pending")
        self.assertEqual(m.hit_chapter, 0)
        self.assertEqual(m.confidence, 0.0)
        self.assertEqual(m.keywords, [])


class TestGenerate(unittest.TestCase):
    def test_empty_arcs_returns_empty(self):
        llm = MagicMock()
        result = generate_arc_milestones(llm, [], "synopsis", "fantasy")
        self.assertEqual(result, [])
        llm.generate_json.assert_not_called()

    def test_clamps_required_by_chapter_to_arc_range(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "milestones": [
                {"milestone_id": "m1_a1", "arc_number": 1,
                 "description": "x", "required_by_chapter": 99,
                 "keywords": ["kw"]},
            ],
        }
        result = generate_arc_milestones(llm, [_arc(1, 1, 5)], "s", "g")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].required_by_chapter, 5)

    def test_skips_malformed(self):
        llm = MagicMock()
        llm.generate_json.return_value = {
            "milestones": [
                {"missing_required_fields": True},
                {"milestone_id": "m1_a1", "arc_number": 1,
                 "description": "ok", "required_by_chapter": 3,
                 "keywords": ["a"]},
            ],
        }
        result = generate_arc_milestones(llm, [_arc()], "s", "g")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].milestone_id, "m1_a1")

    def test_llm_exception_returns_empty(self):
        llm = MagicMock()
        llm.generate_json.side_effect = RuntimeError("timeout")
        result = generate_arc_milestones(llm, [_arc()], "s", "g")
        self.assertEqual(result, [])


class TestCheckInChapter(unittest.TestCase):
    def test_two_keyword_match_marks_hit(self):
        ms = [_milestone(keywords=["thất bại", "sụp đổ", "tan vỡ"])]
        ch = _chapter(2, "Linh trải qua thất bại lớn khi cả vương quốc sụp đổ.")
        newly = check_milestones_in_chapter(ms, ch)
        self.assertEqual(len(newly), 1)
        self.assertEqual(ms[0].status, "hit")
        self.assertEqual(ms[0].hit_chapter, 2)
        self.assertGreater(ms[0].confidence, 0)
        self.assertIn("thất bại", ms[0].evidence.lower())

    def test_single_match_below_threshold_stays_pending(self):
        ms = [_milestone(keywords=["thất bại", "sụp đổ", "tan vỡ"])]
        ch = _chapter(2, "Linh suýt thất bại nhưng vẫn thắng.")
        newly = check_milestones_in_chapter(ms, ch)
        self.assertEqual(newly, [])
        self.assertEqual(ms[0].status, "pending")

    def test_single_keyword_milestone_hits_on_one_match(self):
        ms = [_milestone(keywords=["thức tỉnh"])]
        ch = _chapter(2, "Linh đã thức tỉnh sức mạnh bí ẩn.")
        newly = check_milestones_in_chapter(ms, ch)
        self.assertEqual(len(newly), 1)
        self.assertEqual(ms[0].status, "hit")

    def test_no_keywords_skipped(self):
        ms = [_milestone(keywords=[])]
        ch = _chapter(2, "Anything here")
        newly = check_milestones_in_chapter(ms, ch)
        self.assertEqual(newly, [])
        self.assertEqual(ms[0].status, "pending")

    def test_already_hit_skipped(self):
        ms = [_milestone(keywords=["thất bại", "sụp đổ"])]
        ms[0].status = "hit"
        ms[0].hit_chapter = 1
        ch = _chapter(3, "thất bại sụp đổ")
        newly = check_milestones_in_chapter(ms, ch)
        self.assertEqual(newly, [])
        self.assertEqual(ms[0].hit_chapter, 1)


class TestAudit(unittest.TestCase):
    def test_marks_overdue_pending_as_missed(self):
        ms = [
            _milestone("m1", arc=1, chapter=3),  # overdue
            _milestone("m2", arc=1, chapter=10),  # not yet due
        ]
        audit = audit_arc_milestones(ms, final_chapter=5)
        self.assertEqual(ms[0].status, "missed")
        self.assertEqual(ms[1].status, "pending")
        self.assertEqual(audit["missed"], 1)
        self.assertEqual(audit["pending"], 1)
        self.assertEqual(audit["hit"], 0)
        self.assertEqual(audit["drift_rate"], 0.5)

    def test_all_hit_zero_drift(self):
        ms = [_milestone("m1"), _milestone("m2")]
        for m in ms:
            m.status = "hit"
            m.hit_chapter = 2
        audit = audit_arc_milestones(ms, final_chapter=5)
        self.assertEqual(audit["hit_rate"], 1.0)
        self.assertEqual(audit["drift_rate"], 0.0)

    def test_empty_returns_zeros(self):
        audit = audit_arc_milestones([], final_chapter=5)
        self.assertEqual(audit["total"], 0)
        self.assertEqual(audit["drift_rate"], 0.0)
        self.assertEqual(audit["by_arc"], {})

    def test_by_arc_groups(self):
        ms = [
            _milestone("m1_a1", arc=1, chapter=3),
            _milestone("m2_a1", arc=1, chapter=4),
            _milestone("m1_a2", arc=2, chapter=8),
        ]
        ms[0].status = "hit"
        audit = audit_arc_milestones(ms, final_chapter=5)
        self.assertEqual(audit["by_arc"][1]["total"], 2)
        self.assertEqual(audit["by_arc"][1]["hit"], 1)
        self.assertEqual(audit["by_arc"][1]["missed"], 1)
        self.assertEqual(audit["by_arc"][2]["total"], 1)
        self.assertEqual(audit["by_arc"][2]["pending"], 1)


class TestFormatWarnings(unittest.TestCase):
    def test_all_hit_emits_success(self):
        audit = {"total": 2, "hit": 2, "missed": 0, "pending": 0,
                 "hit_rate": 1.0, "drift_rate": 0.0, "by_arc": {}}
        warns = format_milestone_warnings(audit)
        self.assertTrue(any("✅" in w for w in warns))

    def test_missed_emits_warning(self):
        audit = {"total": 3, "hit": 1, "missed": 2, "pending": 0,
                 "hit_rate": 0.33, "drift_rate": 0.67,
                 "by_arc": {1: {"total": 3, "hit": 1, "missed": 2, "pending": 0}}}
        warns = format_milestone_warnings(audit)
        self.assertTrue(any("⚠️" in w for w in warns))
        self.assertTrue(any("Arc 1" in w for w in warns))

    def test_empty_audit_no_warnings(self):
        self.assertEqual(format_milestone_warnings({"total": 0}), [])


class TestSchemaAndConfig(unittest.TestCase):
    def test_story_draft_has_arc_milestone_fields(self):
        d = StoryDraft(title="t", genre="g")
        self.assertTrue(hasattr(d, "arc_milestones"))
        self.assertEqual(d.arc_milestones, [])
        self.assertTrue(hasattr(d, "arc_milestone_audit"))
        self.assertEqual(d.arc_milestone_audit, {})

    def test_config_flag_default_false(self):
        from config.defaults import PipelineConfig
        cfg = PipelineConfig()
        self.assertFalse(cfg.enable_arc_milestones)


if __name__ == "__main__":
    unittest.main()
