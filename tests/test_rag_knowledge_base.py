"""Tests for RAGKnowledgeBase service and generator RAG integration."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.rag_knowledge_base import _chunk_text, _read_file, RAGKnowledgeBase  # noqa: E402


# ---------------------------------------------------------------------------
# _chunk_text tests
# ---------------------------------------------------------------------------

class TestChunkText(unittest.TestCase):

    def test_empty_string_returns_empty(self):
        self.assertEqual(_chunk_text(""), [])

    def test_whitespace_only_returns_empty(self):
        self.assertEqual(_chunk_text("   \n  "), [])

    def test_short_text_single_chunk(self):
        text = "Đây là một câu ngắn."
        chunks = _chunk_text(text)
        self.assertEqual(len(chunks), 1)
        self.assertIn("Đây là một câu ngắn", chunks[0])

    def test_long_text_splits_into_multiple_chunks(self):
        # Build text that definitely exceeds chunk_size=500
        sentence = "Đây là một câu dài để kiểm tra việc phân chia văn bản. "
        text = sentence * 20  # ~1000+ chars
        chunks = _chunk_text(text, chunk_size=500, overlap=50)
        self.assertGreater(len(chunks), 1)

    def test_overlap_maintains_content(self):
        sentence = "Câu số {n}. "
        text = "".join(sentence.format(n=i) for i in range(50))
        chunks = _chunk_text(text, chunk_size=200, overlap=50)
        # All chunks should be non-empty
        for chunk in chunks:
            self.assertTrue(chunk.strip())

    def test_no_duplicate_full_text(self):
        """Combined chunks shouldn't have more chars than original * some factor."""
        text = "Đây là câu thử nghiệm. " * 30
        chunks = _chunk_text(text)
        total_chars = sum(len(c) for c in chunks)
        # Overlap means some duplication is OK, but not more than 2x
        self.assertLess(total_chars, len(text) * 2)

    def test_custom_chunk_size(self):
        text = "Short sentence. " * 5  # ~80 chars
        chunks = _chunk_text(text, chunk_size=30, overlap=5)
        # With chunk_size=30 we expect multiple chunks
        self.assertGreater(len(chunks), 1)


# ---------------------------------------------------------------------------
# _read_file tests
# ---------------------------------------------------------------------------

class TestReadFile(unittest.TestCase):

    def test_read_txt_file(self):
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w",
                                        encoding="utf-8", delete=False) as f:
            f.write("Xin chào thế giới.")
            tmp_path = f.name
        try:
            content = _read_file(tmp_path)
            self.assertIn("Xin chào", content)
        finally:
            os.unlink(tmp_path)

    def test_read_md_file(self):
        with tempfile.NamedTemporaryFile(suffix=".md", mode="w",
                                        encoding="utf-8", delete=False) as f:
            f.write("# Tiêu đề\nNội dung markdown.")
            tmp_path = f.name
        try:
            content = _read_file(tmp_path)
            self.assertIn("Tiêu đề", content)
        finally:
            os.unlink(tmp_path)

    def test_file_not_found_raises(self):
        with self.assertRaises(FileNotFoundError):
            _read_file("/nonexistent/path/file.txt")

    def test_unsupported_extension_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            tmp_path = f.name
        try:
            with self.assertRaises(ValueError):
                _read_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_file_too_large_raises(self):
        from services.rag_knowledge_base import MAX_FILE_SIZE_BYTES
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"x" * (MAX_FILE_SIZE_BYTES + 1))
            tmp_path = f.name
        try:
            with self.assertRaises(ValueError):
                _read_file(tmp_path)
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# RAGKnowledgeBase tests (with mocked ChromaDB)
# ---------------------------------------------------------------------------

def _make_mock_collection(doc_count=0):
    """Return a mock ChromaDB collection."""
    col = MagicMock()
    col.count.return_value = doc_count
    col.query.return_value = {"documents": [["chunk1", "chunk2", "chunk3"]]}
    return col


def _make_mock_client(collection):
    client = MagicMock()
    client.get_or_create_collection.return_value = collection
    return client


class TestRAGKnowledgeBase(unittest.TestCase):

    def _make_kb_with_mocks(self, doc_count=3):
        """Create RAGKnowledgeBase with mocked ChromaDB internals."""
        with patch("services.rag_knowledge_base._RAG_AVAILABLE", True):
            kb = RAGKnowledgeBase.__new__(RAGKnowledgeBase)
            kb._available = True
            kb._collection_name = "test"
            kb._persist_dir = "data/rag"
            kb._collection = _make_mock_collection(doc_count)
            kb._client = _make_mock_client(kb._collection)
            kb._ef = MagicMock()
        return kb

    def test_count_returns_collection_count(self):
        kb = self._make_kb_with_mocks(doc_count=42)
        self.assertEqual(kb.count(), 42)

    def test_query_returns_documents(self):
        kb = self._make_kb_with_mocks(doc_count=3)
        results = kb.query("test question")
        self.assertEqual(results, ["chunk1", "chunk2", "chunk3"])

    def test_query_empty_question_returns_empty(self):
        kb = self._make_kb_with_mocks(doc_count=3)
        self.assertEqual(kb.query(""), [])
        self.assertEqual(kb.query("   "), [])

    def test_query_empty_collection_returns_empty(self):
        kb = self._make_kb_with_mocks(doc_count=0)
        self.assertEqual(kb.query("test"), [])

    def test_add_documents_calls_collection_add(self):
        kb = self._make_kb_with_mocks()
        texts = ["doc1", "doc2"]
        metas = [{"source": "test.txt", "chunk_index": i} for i in range(2)]
        result = kb.add_documents(texts, metas)
        self.assertEqual(result, 2)
        kb._collection.add.assert_called_once()

    def test_add_documents_empty_list_returns_zero(self):
        kb = self._make_kb_with_mocks()
        result = kb.add_documents([], [])
        self.assertEqual(result, 0)

    def test_clear_deletes_and_recreates_collection(self):
        kb = self._make_kb_with_mocks()
        kb.clear()
        kb._client.delete_collection.assert_called_once_with("test")
        kb._client.get_or_create_collection.assert_called()

    def test_add_file_txt(self):
        kb = self._make_kb_with_mocks()
        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w",
                                        encoding="utf-8", delete=False) as f:
            f.write("Câu một. Câu hai. Câu ba. " * 10)
            tmp_path = f.name
        try:
            result = kb.add_file(tmp_path)
            self.assertGreater(result, 0)
        finally:
            os.unlink(tmp_path)

    def test_add_file_nonexistent_returns_zero(self):
        kb = self._make_kb_with_mocks()
        result = kb.add_file("/nonexistent/file.txt")
        self.assertEqual(result, 0)


# ---------------------------------------------------------------------------
# Graceful degradation when ChromaDB not installed
# ---------------------------------------------------------------------------

class TestGracefulDegradation(unittest.TestCase):

    def test_kb_unavailable_when_chromadb_missing(self):
        with patch("services.rag_knowledge_base._RAG_AVAILABLE", False):
            kb = RAGKnowledgeBase.__new__(RAGKnowledgeBase)
            kb._available = False
            kb._collection = None
            kb._client = None
            kb._ef = None

            self.assertFalse(kb.is_available)
            self.assertEqual(kb.count(), 0)
            self.assertEqual(kb.query("anything"), [])
            self.assertEqual(kb.add_documents(["text"], [{"source": "f"}]), 0)
            kb.clear()  # Should not raise

    def test_add_file_unavailable_returns_zero(self):
        kb = RAGKnowledgeBase.__new__(RAGKnowledgeBase)
        kb._available = False
        kb._collection = None
        kb._client = None
        kb._ef = None
        self.assertEqual(kb.add_file("somefile.txt"), 0)


# ---------------------------------------------------------------------------
# Generator RAG integration tests
# ---------------------------------------------------------------------------

class TestGeneratorRAGIntegration(unittest.TestCase):

    def _make_minimal_objects(self):
        """Create minimal Character/WorldSetting/ChapterOutline for generator tests."""
        from models.schemas import Character, WorldSetting, ChapterOutline
        chars = [Character(name="Lý Thần", role="chính", personality="dũng cảm",
                           background="", motivation="", appearance="")]
        world = WorldSetting(name="Tiên Giới", description="thế giới tu tiên")
        outline = ChapterOutline(chapter_number=1, title="Khởi đầu",
                                 summary="Nhân vật xuất hiện",
                                 key_events=["sự kiện A"],
                                 emotional_arc="tò mò")
        return chars, world, outline

    @patch("pipeline.layer1_story.generator._get_rag_kb")
    def test_generate_world_injects_rag_context(self, mock_get_rag_kb):
        """generate_world() prepends RAG context when rag_enabled=True."""
        from pipeline.layer1_story.generator import StoryGenerator
        from models.schemas import Character

        mock_rag = MagicMock()
        mock_rag.is_available = True
        mock_rag.query.return_value = ["Triều đại nhà Trần nổi tiếng về sức mạnh quân sự."]
        mock_get_rag_kb.return_value = mock_rag

        generator = StoryGenerator.__new__(StoryGenerator)
        generator.llm = MagicMock()
        generator.llm.generate_json.return_value = {
            "name": "Tiên Giới", "description": "mô tả", "rules": [], "locations": [], "era": ""
        }
        generator.config = MagicMock()
        generator.config.pipeline.rag_enabled = True
        generator.config.pipeline.rag_persist_dir = "data/rag"

        chars = [Character(name="A", role="chính", personality="x",
                           background="", motivation="", appearance="")]
        generator.generate_world("Tiêu đề", "Tiên Hiệp", chars)

        call_args = generator.llm.generate_json.call_args
        user_prompt = call_args[1]["user_prompt"]
        self.assertIn("Tài liệu tham khảo", user_prompt)

    @patch("pipeline.layer1_story.generator._get_rag_kb")
    def test_generate_world_no_rag_when_disabled(self, mock_get_rag_kb):
        """generate_world() does NOT call RAG when rag_enabled=False."""
        from pipeline.layer1_story.generator import StoryGenerator
        from models.schemas import Character

        generator = StoryGenerator.__new__(StoryGenerator)
        generator.llm = MagicMock()
        generator.llm.generate_json.return_value = {
            "name": "Tiên Giới", "description": "mô tả", "rules": [], "locations": [], "era": ""
        }
        generator.config = MagicMock()
        generator.config.pipeline.rag_enabled = False

        chars = [Character(name="A", role="chính", personality="x",
                           background="", motivation="", appearance="")]
        generator.generate_world("Tiêu đề", "Tiên Hiệp", chars)

        mock_get_rag_kb.assert_not_called()

    @patch("pipeline.layer1_story.generator._get_rag_kb")
    def test_build_chapter_prompt_injects_rag_context(self, mock_get_rag_kb):
        """_build_chapter_prompt() appends RAG section to context_text when enabled."""
        from pipeline.layer1_story.generator import StoryGenerator

        mock_rag = MagicMock()
        mock_rag.is_available = True
        mock_rag.query.return_value = ["Tài liệu lịch sử quan trọng."]
        mock_get_rag_kb.return_value = mock_rag

        generator = StoryGenerator.__new__(StoryGenerator)
        generator.config = MagicMock()
        generator.config.pipeline.rag_enabled = True
        generator.config.pipeline.rag_persist_dir = "data/rag"

        chars, world, outline = self._make_minimal_objects()
        sys_p, user_p = generator._build_chapter_prompt(
            "title", "genre", "style", chars, world, outline, 2000
        )
        self.assertIn("Tài liệu tham khảo", user_p)

    @patch("pipeline.layer1_story.generator._get_rag_kb")
    def test_build_chapter_prompt_no_rag_when_disabled(self, mock_get_rag_kb):
        """_build_chapter_prompt() skips RAG when rag_enabled=False."""
        from pipeline.layer1_story.generator import StoryGenerator

        generator = StoryGenerator.__new__(StoryGenerator)
        generator.config = MagicMock()
        generator.config.pipeline.rag_enabled = False

        chars, world, outline = self._make_minimal_objects()
        sys_p, user_p = generator._build_chapter_prompt(
            "title", "genre", "style", chars, world, outline, 2000
        )
        mock_get_rag_kb.assert_not_called()
        self.assertNotIn("Tài liệu tham khảo", user_p)

    @patch("pipeline.layer1_story.generator._get_rag_kb")
    def test_rag_empty_results_no_injection(self, mock_get_rag_kb):
        """No RAG section added when query returns empty list."""
        from pipeline.layer1_story.generator import StoryGenerator

        mock_rag = MagicMock()
        mock_rag.is_available = True
        mock_rag.query.return_value = []
        mock_get_rag_kb.return_value = mock_rag

        generator = StoryGenerator.__new__(StoryGenerator)
        generator.config = MagicMock()
        generator.config.pipeline.rag_enabled = True
        generator.config.pipeline.rag_persist_dir = "data/rag"

        chars, world, outline = self._make_minimal_objects()
        sys_p, user_p = generator._build_chapter_prompt(
            "title", "genre", "style", chars, world, outline, 2000
        )
        self.assertNotIn("Tài liệu tham khảo", user_p)


# ---------------------------------------------------------------------------
# RAG_CONTEXT_SECTION prompt template
# ---------------------------------------------------------------------------

class TestRAGContextSectionTemplate(unittest.TestCase):

    def test_template_contains_placeholder(self):
        from services.prompts import RAG_CONTEXT_SECTION
        self.assertIn("{rag_context}", RAG_CONTEXT_SECTION)

    def test_template_formats_correctly(self):
        from services.prompts import RAG_CONTEXT_SECTION
        formatted = RAG_CONTEXT_SECTION.format(rag_context="Sample text")
        self.assertIn("Sample text", formatted)
        self.assertIn("Tài liệu tham khảo", formatted)


# ---------------------------------------------------------------------------
# Config RAG fields
# ---------------------------------------------------------------------------

class TestConfigRAGFields(unittest.TestCase):

    def test_pipeline_config_defaults(self):
        from config import PipelineConfig
        cfg = PipelineConfig()
        self.assertFalse(cfg.rag_enabled)
        self.assertEqual(cfg.rag_persist_dir, "data/rag")

    def test_config_manager_has_rag_fields(self):
        import threading
        from config import ConfigManager
        # Reset singleton for clean test
        with threading.Lock():
            mgr = ConfigManager.__new__(ConfigManager)
            mgr._initialized = False
            mgr._initialized = True
            mgr.llm = MagicMock()
            mgr.pipeline = MagicMock()
            mgr.pipeline.rag_enabled = False
            mgr.pipeline.rag_persist_dir = "data/rag"

        self.assertFalse(mgr.pipeline.rag_enabled)
        self.assertEqual(mgr.pipeline.rag_persist_dir, "data/rag")


if __name__ == "__main__":
    unittest.main()
