"""Test PDFExporter service."""
import os
from models.schemas import StoryDraft, Chapter, Character
from services.pdf_exporter import PDFExporter


def _make_story(word_count=1000):
    content = "word " * word_count
    return StoryDraft(
        title="Test Story", genre="Fantasy",
        chapters=[Chapter(chapter_number=1, title="Ch1", content=content, word_count=word_count)],
    )


def test_compute_reading_stats():
    story = _make_story(1000)
    stats = PDFExporter.compute_reading_stats(story)
    assert stats.total_words == 1000
    assert stats.total_chapters == 1
    assert stats.estimated_reading_minutes == 5  # ~200 wpm
    assert stats.avg_words_per_chapter == 1000


def test_compute_stats_multi_chapter():
    story = StoryDraft(title="T", genre="G", chapters=[
        Chapter(chapter_number=i, title=f"Ch{i}", content="word " * 500)
        for i in range(1, 4)
    ])
    stats = PDFExporter.compute_reading_stats(story)
    assert stats.total_chapters == 3
    assert stats.total_words == 1500


def test_export_creates_file(tmp_path):
    story = _make_story(50)
    path = PDFExporter.export(story, str(tmp_path / "test.pdf"))
    assert path != ""
    assert os.path.exists(path)


def test_export_with_characters(tmp_path):
    story = _make_story(50)
    chars = [Character(name="Minh", role="protagonist", personality="brave", background="bg", motivation="m")]
    path = PDFExporter.export(story, str(tmp_path / "test2.pdf"), characters=chars)
    assert os.path.exists(path)


def test_export_empty_story(tmp_path):
    story = StoryDraft(title="Empty", genre="G", chapters=[])
    path = PDFExporter.export(story, str(tmp_path / "empty.pdf"))
    assert os.path.exists(path)
