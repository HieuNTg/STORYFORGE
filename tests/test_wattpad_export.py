"""Tests for Wattpad export ZIP bundle, character appendix, and reading time."""
import os
import zipfile
from models.schemas import StoryDraft, Chapter, Character, WorldSetting, ChapterOutline
from services.wattpad_exporter import PlatformExporter


class TestWattpadExport:
    def _make_story(self, title="Test Story", with_characters=True):
        chapters = [
            Chapter(chapter_number=1, title="Ch1", content="Hello world " * 100, word_count=200),
            Chapter(chapter_number=2, title="Ch2", content="Second chapter " * 50, word_count=100),
        ]
        characters = []
        if with_characters:
            characters = [
                Character(name="Alice", role="main", personality="brave", background="hero", motivation="save world"),
            ]
        return StoryDraft(
            title=title,
            genre="fantasy",
            synopsis="A test story",
            chapters=chapters,
            characters=characters,
            outlines=[
                ChapterOutline(chapter_number=1, title="Ch1", summary="s1"),
                ChapterOutline(chapter_number=2, title="Ch2", summary="s2"),
            ],
            world=WorldSetting(name="TestWorld", description="A test world"),
        )

    def test_export_creates_zip(self, tmp_path):
        story = self._make_story()
        result = PlatformExporter.export_wattpad(story, output_dir=str(tmp_path))
        assert "zip_path" in result
        assert os.path.exists(result["zip_path"])
        assert result["zip_path"].endswith("_wattpad.zip")
        with zipfile.ZipFile(result["zip_path"], "r") as zf:
            names = zf.namelist()
            assert "metadata.json" in names
            assert "full_story.txt" in names
            assert "chapter_001.html" in names

    def test_character_appendix_included(self, tmp_path):
        story = self._make_story(with_characters=True)
        PlatformExporter.export_wattpad(story, output_dir=str(tmp_path))
        char_path = os.path.join(str(tmp_path), "characters.txt")
        assert os.path.exists(char_path)
        content = open(char_path, encoding="utf-8").read()
        assert "Alice" in content

    def test_no_character_appendix_without_characters(self, tmp_path):
        story = self._make_story(with_characters=False)
        PlatformExporter.export_wattpad(story, output_dir=str(tmp_path))
        char_path = os.path.join(str(tmp_path), "characters.txt")
        assert not os.path.exists(char_path)

    def test_reading_time_in_metadata(self, tmp_path):
        story = self._make_story()
        result = PlatformExporter.export_wattpad(story, output_dir=str(tmp_path))
        meta = result["metadata"]
        for cd in meta["chapter_details"]:
            assert "reading_time_min" in cd
            assert cd["reading_time_min"] >= 1

    def test_empty_title_fallback(self, tmp_path):
        story = self._make_story(title="   ")
        result = PlatformExporter.export_wattpad(story, output_dir=str(tmp_path))
        assert "story_wattpad.zip" in result["zip_path"]
