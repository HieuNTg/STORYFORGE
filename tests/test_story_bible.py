"""Tests cho Story Bible system và Genre Library."""

import sys
import unittest
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.schemas import (  # noqa: E402
    StoryBible, StoryDraft,
    Chapter, CharacterState, PlotEvent, WorldSetting, Character,
)
from pipeline.layer1_story.story_bible_manager import StoryBibleManager  # noqa: E402
from services.genre_library import get_genre, get_genre_by_name, list_genres, GENRE_LIBRARY  # noqa: E402


def _make_draft(num_outlines: int = 60) -> StoryDraft:
    """Tạo StoryDraft giả cho test."""
    from models.schemas import ChapterOutline
    draft = StoryDraft(
        title="Kiếm Thần Vô Song",
        genre="Tiên Hiệp",
        synopsis="Một thiếu niên nghèo khó bước lên con đường tu tiên.",
        world=WorldSetting(
            name="Lục Địa Tu Tiên",
            description="Thế giới nơi linh khí tràn ngập",
            rules=["Mạnh thắng yếu", "Linh khí là nguồn sức mạnh"],
        ),
        characters=[
            Character(name="Lý Vân", role="chính", personality="cương nghị",
                      background="mồ côi", motivation="báo thù"),
        ],
    )
    for i in range(1, num_outlines + 1):
        draft.outlines.append(ChapterOutline(
            chapter_number=i,
            title=f"Chương {i}",
            summary=f"Tóm tắt chương {i}",
        ))
    return draft


def _make_chapter(num: int, summary: str = "") -> Chapter:
    return Chapter(
        chapter_number=num,
        title=f"Chương {num}",
        content=f"Nội dung chương {num}.",
        word_count=500,
        summary=summary or f"Tóm tắt ch{num}",
    )


def _make_event(ch: int, desc: str, chars: list[str] = None) -> PlotEvent:
    return PlotEvent(
        chapter_number=ch,
        event=desc,
        characters_involved=chars or [],
    )


class TestStoryBibleInitialization(unittest.TestCase):
    """Test khởi tạo StoryBible từ draft."""

    def setUp(self):
        self.manager = StoryBibleManager()
        self.draft = _make_draft(60)

    def test_initialize_creates_bible(self):
        bible = self.manager.initialize(self.draft, arc_size=30)
        self.assertIsInstance(bible, StoryBible)

    def test_premise_from_synopsis(self):
        bible = self.manager.initialize(self.draft)
        self.assertIn("thiếu niên", bible.premise)

    def test_world_rules_copied(self):
        bible = self.manager.initialize(self.draft)
        self.assertIn("Mạnh thắng yếu", bible.world_rules)

    def test_arcs_created_correctly(self):
        bible = self.manager.initialize(self.draft, arc_size=30)
        # 60 outlines / 30 per arc = 2 arcs
        self.assertEqual(len(bible.arcs), 2)
        self.assertEqual(bible.arcs[0].start_chapter, 1)
        self.assertEqual(bible.arcs[0].end_chapter, 30)
        self.assertEqual(bible.arcs[1].start_chapter, 31)
        self.assertEqual(bible.arcs[1].end_chapter, 60)

    def test_arc_status_initially_active(self):
        bible = self.manager.initialize(self.draft)
        for arc in bible.arcs:
            self.assertEqual(arc.status, "active")


class TestStoryBibleUpdateAfterChapter(unittest.TestCase):
    """Test cập nhật bible sau mỗi chương."""

    def setUp(self):
        self.manager = StoryBibleManager()
        self.draft = _make_draft(60)
        self.bible = self.manager.initialize(self.draft, arc_size=30)

    def test_threads_added_from_events(self):
        ch = _make_chapter(5, "Lý Vân đột phá cảnh giới")
        events = [_make_event(5, "Lý Vân đột phá", ["Lý Vân"])]
        self.manager.update_after_chapter(self.bible, ch, [], events)
        self.assertEqual(len(self.bible.active_threads), 1)
        self.assertIn("Lý Vân đột phá", self.bible.active_threads[0].description)

    def test_milestone_events_tracked(self):
        ch = _make_chapter(5)
        events = [_make_event(5, "Đại chiến hoàng thành")]
        self.manager.update_after_chapter(self.bible, ch, [], events)
        self.assertTrue(any("Đại chiến" in m for m in self.bible.milestone_events))

    def test_old_threads_auto_resolved_at_21(self):
        """Khi có >20 threads, threads cũ phải resolved."""
        for i in range(1, 22):
            ch = _make_chapter(i)
            events = [_make_event(i, f"Sự kiện {i}")]
            self.manager.update_after_chapter(self.bible, ch, [], events)
        # Active threads capped at 20
        self.assertLessEqual(len(self.bible.active_threads), 20)
        # Oldest moved to resolved
        self.assertGreater(len(self.bible.resolved_threads), 0)

    def test_arc_completion_detected(self):
        """Khi viết chương 30, arc 1 phải completed."""
        ch = _make_chapter(30, "Kết thúc arc 1")
        self.manager.update_after_chapter(self.bible, ch, [], [])
        arc1 = self.bible.arcs[0]
        self.assertEqual(arc1.status, "completed")
        self.assertTrue(len(self.bible.arc_summaries) > 0)

    def test_milestone_events_capped_at_30(self):
        """Milestone events không vượt quá 30."""
        for i in range(1, 40):
            ch = _make_chapter(i)
            events = [_make_event(i, f"Sự kiện milestone {i}")]
            self.manager.update_after_chapter(self.bible, ch, [], events)
        self.assertLessEqual(len(self.bible.milestone_events), 30)


class TestStoryBibleContextBuilding(unittest.TestCase):
    """Test xây dựng context string từ bible."""

    def setUp(self):
        self.manager = StoryBibleManager()
        self.draft = _make_draft(60)
        self.bible = self.manager.initialize(self.draft, arc_size=30)

    def test_context_includes_premise(self):
        ctx = self.manager.get_context_for_chapter(self.bible, 5)
        self.assertIn("Tiền đề", ctx)

    def test_context_includes_world_rules(self):
        ctx = self.manager.get_context_for_chapter(self.bible, 5)
        self.assertIn("Mạnh thắng yếu", ctx)

    def test_context_includes_current_arc(self):
        ctx = self.manager.get_context_for_chapter(self.bible, 5)
        self.assertIn("Arc hiện tại", ctx)

    def test_context_includes_active_threads(self):
        ch = _make_chapter(5)
        events = [_make_event(5, "Lý Vân nhập môn tông phái")]
        self.manager.update_after_chapter(self.bible, ch, [], events)
        ctx = self.manager.get_context_for_chapter(self.bible, 6)
        self.assertIn("Tuyến truyện đang mở", ctx)

    def test_context_includes_recent_summaries(self):
        ctx = self.manager.get_context_for_chapter(
            self.bible, 5,
            recent_summaries=["Tóm tắt ch4", "Tóm tắt ch5"],
        )
        self.assertIn("Tóm tắt ch4", ctx)

    def test_context_includes_character_states(self):
        states = [CharacterState(name="Lý Vân", mood="quyết tâm", arc_position="rising", last_action="tu luyện")]
        ctx = self.manager.get_context_for_chapter(self.bible, 5, character_states=states)
        self.assertIn("Lý Vân", ctx)

    def test_context_includes_arc_summaries_after_completion(self):
        ch = _make_chapter(30, "Arc 1 hoàn tất")
        self.manager.update_after_chapter(self.bible, ch, [], [])
        ctx = self.manager.get_context_for_chapter(self.bible, 31)
        self.assertIn("Tóm tắt các arc trước", ctx)


class TestGenreLibrary(unittest.TestCase):
    """Test thư viện thể loại truyện."""

    def test_list_genres_returns_all(self):
        genres = list_genres()
        self.assertEqual(len(genres), len(GENRE_LIBRARY))

    def test_list_genres_has_required_keys(self):
        for g in list_genres():
            self.assertIn("key", g)
            self.assertIn("name", g)
            self.assertIn("description", g)

    def test_get_genre_by_key(self):
        tien_hiep = get_genre("tien_hiep")
        self.assertEqual(tien_hiep["name"], "Tiên Hiệp")
        self.assertIn("vocab", tien_hiep)
        self.assertIn("arc_template", tien_hiep)

    def test_get_genre_fallback_on_unknown(self):
        result = get_genre("unknown_genre_xyz")
        # Falls back to tien_hiep
        self.assertEqual(result["name"], "Tiên Hiệp")

    def test_get_genre_by_name_found(self):
        result = get_genre_by_name("Ngôn Tình")
        self.assertIsNotNone(result)
        self.assertIn("contract marriage", result["tropes"])

    def test_get_genre_by_name_case_insensitive(self):
        result = get_genre_by_name("ngôn tình")
        self.assertIsNotNone(result)

    def test_get_genre_by_name_not_found(self):
        result = get_genre_by_name("Thể Loại Không Tồn Tại")
        self.assertIsNone(result)

    def test_all_genres_have_typical_chapters(self):
        for key, genre in GENRE_LIBRARY.items():
            self.assertIn("typical_chapters", genre, f"{key} missing typical_chapters")
            self.assertGreater(genre["typical_chapters"], 0)

    def test_tien_hiep_has_correct_data(self):
        g = get_genre("tien_hiep")
        self.assertIn("tu luyện", g["vocab"])
        self.assertEqual(g["typical_chapters"], 300)
        self.assertEqual(g["words_per_chapter"], 3000)


class TestStoryDraftBibleField(unittest.TestCase):
    """Test StoryDraft có field story_bible."""

    def test_story_draft_has_story_bible_field(self):
        draft = StoryDraft(title="Test", genre="Tiên Hiệp")
        self.assertTrue(hasattr(draft, "story_bible"))
        self.assertIsNone(draft.story_bible)

    def test_story_draft_accepts_bible(self):
        draft = StoryDraft(title="Test", genre="Tiên Hiệp")
        draft.story_bible = StoryBible(premise="Test premise")
        self.assertEqual(draft.story_bible.premise, "Test premise")


if __name__ == "__main__":
    unittest.main()
