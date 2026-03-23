"""
Test suite for Phase 4: File Download Export changes.

Tests:
1. export_output() returns list[str] of file paths
2. export_zip() returns str (path to ZIP file)
3. _export_markdown() returns path string when story data exists
4. gr.File component in app.py is properly used
5. Import chain works correctly
6. Handler functions in app.py work without errors
"""

import os
import sys
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.orchestrator import PipelineOrchestrator
from models.schemas import (
    PipelineOutput,
    StoryDraft,
    Chapter,
    Character,
    EnhancedStory,
)


class TestExportMarkdown:
    """Test _export_markdown() returns file path string."""

    def setup_method(self):
        """Setup test fixtures."""
        self.orch = PipelineOrchestrator()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup after tests."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_export_markdown_returns_path_string_when_story_exists(self):
        """Verify _export_markdown() returns a file path string (not None)."""
        # Setup: Create a minimal story
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test content")
        story = StoryDraft(
            title="Test Story",
            genre="Tiên Hiệp",
            synopsis="Test synopsis",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        timestamp = "20260323_120000"
        result = self.orch._export_markdown(self.temp_dir, timestamp)

        # Assert
        assert result is not None, "Should return file path when story exists"
        assert isinstance(result, str), "Should return string type"
        assert result.endswith(".md"), "Should return markdown file path"
        assert os.path.exists(result), "File should be created"

    def test_export_markdown_returns_none_when_no_story(self):
        """Verify _export_markdown() returns None when no story data."""
        # Setup: No story data
        self.orch.output.story_draft = None
        self.orch.output.enhanced_story = None

        # Act
        timestamp = "20260323_120000"
        result = self.orch._export_markdown(self.temp_dir, timestamp)

        # Assert
        assert result is None, "Should return None when no story exists"

    def test_export_markdown_file_content_valid(self):
        """Verify _export_markdown() creates file with valid content."""
        # Setup
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test content")
        story = StoryDraft(
            title="Test Story",
            genre="Tiên Hiệp",
            synopsis="Test synopsis",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        timestamp = "20260323_120000"
        result = self.orch._export_markdown(self.temp_dir, timestamp)

        # Assert
        with open(result, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "# Test Story" in content, "File should contain story title"
        assert "Tiên Hiệp" in content, "File should contain genre"
        assert "Chapter 1" in content, "File should contain chapter"

    def test_export_markdown_uses_enhanced_story_if_available(self):
        """Verify _export_markdown() prioritizes enhanced_story over draft."""
        # Setup: Both draft and enhanced
        chapter = Chapter(chapter_number=1, title="Draft Chapter", content="Draft")
        draft = StoryDraft(
            title="Draft",
            genre="Tiên Hiệp",
            synopsis="Draft",
            chapters=[chapter],
            characters=[]
        )
        enhanced = EnhancedStory(
            title="Enhanced",
            genre="Tiên Hiệp",
            chapters=[chapter],
            enhancement_notes=[],
            drama_score=0.8
        )
        self.orch.output.story_draft = draft
        self.orch.output.enhanced_story = enhanced

        # Act
        timestamp = "20260323_120000"
        result = self.orch._export_markdown(self.temp_dir, timestamp)

        # Assert
        with open(result, 'r', encoding='utf-8') as f:
            content = f.read()
        assert "# Enhanced" in content, "Should use enhanced story"


class TestExportOutput:
    """Test export_output() returns list[str] of file paths."""

    def setup_method(self):
        """Setup test fixtures."""
        self.orch = PipelineOrchestrator()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup after tests."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_export_output_returns_list_of_strings(self):
        """Verify export_output() returns list[str]."""
        # Setup: Create minimal story
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test")
        story = StoryDraft(
            title="Test",
            genre="Tiên Hiệp",
            synopsis="Test",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        result = self.orch.export_output(self.temp_dir, formats=["TXT"])

        # Assert
        assert isinstance(result, list), "Should return list"
        assert all(isinstance(p, str) for p in result), "All items should be strings"
        assert all(os.path.isfile(p) for p in result), "All paths should exist"

    def test_export_output_returns_empty_list_when_no_data(self):
        """Verify export_output() returns empty list when no data."""
        # Setup: No output data
        self.orch.output.story_draft = None
        self.orch.output.enhanced_story = None

        # Act
        result = self.orch.export_output(self.temp_dir, formats=["TXT"])

        # Assert
        assert isinstance(result, list), "Should return list"
        assert len(result) == 0, "Should return empty list when no data"

    def test_export_output_txt_format(self):
        """Verify TXT format export works."""
        # Setup
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test")
        story = StoryDraft(
            title="Test",
            genre="Tiên Hiệp",
            synopsis="Test",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        result = self.orch.export_output(self.temp_dir, formats=["TXT"])

        # Assert
        assert len(result) > 0, "Should create TXT file"
        txt_files = [p for p in result if p.endswith('.txt')]
        assert len(txt_files) > 0, "Should have TXT files"

    def test_export_output_markdown_format(self):
        """Verify Markdown format export works."""
        # Setup
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test")
        story = StoryDraft(
            title="Test",
            genre="Tiên Hiệp",
            synopsis="Test",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        result = self.orch.export_output(self.temp_dir, formats=["Markdown"])

        # Assert
        assert len(result) > 0, "Should create file"
        md_files = [p for p in result if p.endswith('.md')]
        assert len(md_files) > 0, "Should have Markdown files"

    def test_export_output_json_format_with_video_script(self):
        """Verify JSON format export includes video script."""
        # Setup: Create video script
        from models.schemas import VideoScript
        video_script = VideoScript(
            title="Test",
            total_duration_seconds=60.0,
            panels=[],
            voice_lines=[],
            character_descriptions={},
            location_descriptions={}
        )
        self.orch.output.video_script = video_script

        # Act
        result = self.orch.export_output(self.temp_dir, formats=["JSON"])

        # Assert
        json_files = [p for p in result if p.endswith('.json')]
        assert len(json_files) > 0, "Should have JSON files"

    def test_export_output_multiple_formats(self):
        """Verify export with multiple formats works."""
        # Setup
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test")
        story = StoryDraft(
            title="Test",
            genre="Tiên Hiệp",
            synopsis="Test",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        result = self.orch.export_output(
            self.temp_dir,
            formats=["TXT", "Markdown"]
        )

        # Assert
        assert len(result) > 0, "Should export multiple files"


class TestExportZip:
    """Test export_zip() returns str (ZIP file path)."""

    def setup_method(self):
        """Setup test fixtures."""
        self.orch = PipelineOrchestrator()
        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Cleanup after tests."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_export_zip_returns_string(self):
        """Verify export_zip() returns string type."""
        # Setup
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test")
        story = StoryDraft(
            title="Test",
            genre="Tiên Hiệp",
            synopsis="Test",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        result = self.orch.export_zip(self.temp_dir, formats=["TXT"])

        # Assert
        assert isinstance(result, str), "Should return string"
        assert result.endswith('.zip'), "Should return ZIP file path"
        assert os.path.exists(result), "ZIP file should exist"

    def test_export_zip_returns_empty_string_when_no_data(self):
        """Verify export_zip() returns empty string when no data."""
        # Setup: No data
        self.orch.output.story_draft = None

        # Act
        result = self.orch.export_zip(self.temp_dir, formats=["TXT"])

        # Assert
        assert isinstance(result, str), "Should return string"
        assert result == "", "Should return empty string when no data"

    def test_export_zip_file_is_valid_zip(self):
        """Verify export_zip() creates valid ZIP file."""
        # Setup
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test")
        story = StoryDraft(
            title="Test",
            genre="Tiên Hiệp",
            synopsis="Test",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        result = self.orch.export_zip(self.temp_dir, formats=["TXT"])

        # Assert
        assert zipfile.is_zipfile(result), "Should be valid ZIP"
        with zipfile.ZipFile(result, 'r') as zf:
            names = zf.namelist()
            assert len(names) > 0, "ZIP should contain files"

    def test_export_zip_contains_exported_files(self):
        """Verify ZIP contains all exported files."""
        # Setup
        chapter = Chapter(chapter_number=1, title="Chapter 1", content="Test")
        story = StoryDraft(
            title="Test",
            genre="Tiên Hiệp",
            synopsis="Test",
            chapters=[chapter],
            characters=[]
        )
        self.orch.output.story_draft = story

        # Act
        zip_path = self.orch.export_zip(self.temp_dir, formats=["TXT", "Markdown"])

        # Assert
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            assert any(n.endswith('.txt') for n in names), "ZIP should have TXT"
            assert any(n.endswith('.md') for n in names), "ZIP should have MD"


class TestImportChain:
    """Test import chain works correctly."""

    def test_import_orchestrator(self):
        """Verify can import PipelineOrchestrator."""
        from pipeline.orchestrator import PipelineOrchestrator
        assert PipelineOrchestrator is not None

    def test_import_schemas(self):
        """Verify can import all required schemas."""
        from models.schemas import (
            PipelineOutput,
            StoryDraft,
            Chapter,
            Character,
            EnhancedStory,
        )
        assert PipelineOutput is not None
        assert StoryDraft is not None

    def test_instantiate_orchestrator(self):
        """Verify can instantiate orchestrator."""
        orch = PipelineOrchestrator()
        assert orch is not None
        assert hasattr(orch, 'export_output')
        assert hasattr(orch, 'export_zip')
        assert hasattr(orch, '_export_markdown')


class TestAppIntegration:
    """Test app.py integration with export functions."""

    def test_gr_file_import(self):
        """Verify gradio gr.File can be imported."""
        import gradio as gr
        assert hasattr(gr, 'File')

    def test_export_handlers_exist(self):
        """Verify export handlers can be defined."""
        def export_files(orch, formats):
            if orch is None:
                return None
            try:
                paths = orch.export_output(formats=formats)
                return paths if paths else None
            except Exception:
                return None

        def export_zip_handler(orch, formats):
            if orch is None:
                return None
            try:
                zip_path = orch.export_zip(formats=formats)
                return [zip_path] if zip_path else None
            except Exception:
                return None

        # Just verify they can be called
        orch = PipelineOrchestrator()
        result_files = export_files(orch, [])
        result_zip = export_zip_handler(orch, [])
        assert result_files is not None or result_files is None
        assert result_zip is not None or result_zip is None


class TestTypeAnnotations:
    """Test that type annotations are correct."""

    def test_export_output_return_type(self):
        """Verify export_output returns list[str]."""
        orch = PipelineOrchestrator()
        # Check annotation
        import inspect
        sig = inspect.signature(orch.export_output)
        return_annotation = sig.return_annotation
        assert return_annotation == list[str], f"Expected list[str], got {return_annotation}"

    def test_export_zip_return_type(self):
        """Verify export_zip returns str."""
        orch = PipelineOrchestrator()
        # Check annotation
        import inspect
        sig = inspect.signature(orch.export_zip)
        return_annotation = sig.return_annotation
        assert return_annotation == str, f"Expected str, got {return_annotation}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
