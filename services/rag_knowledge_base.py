"""RAG Knowledge Base service using ChromaDB + sentence-transformers.

Graceful degradation: if chromadb or sentence-transformers are not installed,
all operations silently no-op and query() returns [].

ChromaDB persistence configuration
-----------------------------------
CHROMA_PERSIST_DIR   (env var, default: "data/chromadb")
    Directory where ChromaDB stores its on-disk data.  Overrides the
    persist_dir constructor argument when set.

CHROMA_COLLECTION_NAME   (env var, default: "storyforge_world")
    Name of the default ChromaDB collection used for world-building context.
    Overrides the collection_name constructor argument when set.

These can also be set in config.py (pipeline.rag_persist_dir) and will be
picked up automatically when RAGKnowledgeBase is instantiated via
get_rag_kb() in pipeline/layer1_story/context_helpers.py.
"""

import hashlib
import logging
import os
import re
from typing import Optional

# ---------------------------------------------------------------------------
# ChromaDB persistence defaults (can be overridden via env vars)
# ---------------------------------------------------------------------------
CHROMA_PERSIST_DIR: str = os.environ.get("CHROMA_PERSIST_DIR", "data/chromadb")
CHROMA_COLLECTION_NAME: str = os.environ.get("CHROMA_COLLECTION_NAME", "storyforge_world")

logger = logging.getLogger(__name__)

# Optional imports — graceful degradation if not installed
try:
    import chromadb
    from chromadb.utils import embedding_functions
    _CHROMADB_AVAILABLE = True
except ImportError:
    _CHROMADB_AVAILABLE = False
    logger.debug("chromadb not installed — RAG disabled")

try:
    from sentence_transformers import SentenceTransformer  # noqa: F401
    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    _SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.debug("sentence-transformers not installed — RAG disabled")

_RAG_AVAILABLE = _CHROMADB_AVAILABLE and _SENTENCE_TRANSFORMERS_AVAILABLE

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks, preferring sentence boundaries.

    Strategy:
    1. Split on sentence-ending punctuation (. ! ? newlines).
    2. Accumulate sentences until chunk_size reached.
    3. When starting the next chunk, back-track by `overlap` chars.
    """
    if not text or not text.strip():
        return []

    # Split on sentence boundaries (keep delimiter attached)
    sentence_pattern = re.compile(r"(?<=[.!?\n])\s+")
    sentences = sentence_pattern.split(text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return []

    chunks: list[str] = []
    current_chars = 0
    current_sentences: list[str] = []

    for sentence in sentences:
        sentence_len = len(sentence)

        if current_chars + sentence_len > chunk_size and current_sentences:
            # Emit current chunk
            chunk_text = " ".join(current_sentences)
            chunks.append(chunk_text)

            # Build overlap: take trailing sentences that fit in `overlap` chars
            overlap_sentences: list[str] = []
            overlap_chars = 0
            for s in reversed(current_sentences):
                if overlap_chars + len(s) <= overlap:
                    overlap_sentences.insert(0, s)
                    overlap_chars += len(s) + 1
                else:
                    break

            current_sentences = overlap_sentences
            current_chars = overlap_chars

        current_sentences.append(sentence)
        current_chars += sentence_len + 1  # +1 for space

    # Emit last chunk
    if current_sentences:
        chunks.append(" ".join(current_sentences))

    return chunks


def _read_file(filepath: str) -> str:
    """Read .txt, .md, or .pdf file. Returns text content."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    size = os.path.getsize(filepath)
    if size > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File too large ({size} bytes). Max {MAX_FILE_SIZE_BYTES} bytes.")

    ext = os.path.splitext(filepath)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")

    if ext in (".txt", ".md"):
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(filepath)
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n".join(pages)
        except ImportError:
            raise ImportError("pypdf is required to read PDF files. Install with: pip install pypdf")

    return ""  # unreachable


class RAGKnowledgeBase:
    """Vector knowledge base for reference document retrieval.

    Usage:
        kb = RAGKnowledgeBase()
        kb.add_file("history.pdf")
        results = kb.query("Lịch sử triều đại nhà Trần")
    """

    def __init__(
        self,
        collection_name: str = CHROMA_COLLECTION_NAME,
        persist_dir: str = CHROMA_PERSIST_DIR,
    ):
        self._available = _RAG_AVAILABLE
        self._collection_name = collection_name
        self._persist_dir = persist_dir
        self._client: Optional[object] = None
        self._collection: Optional[object] = None
        self._ef: Optional[object] = None

        if self._available:
            self._init_client()

    def _init_client(self) -> None:
        """Initialize ChromaDB persistent client and embedding function.

        Storage location is determined by (in priority order):
          1. Constructor argument persist_dir (set from context_helpers.get_rag_kb)
          2. CHROMA_PERSIST_DIR environment variable
          3. Module-level default "data/chromadb"

        Collection name follows the same priority via CHROMA_COLLECTION_NAME.
        Using chromadb.PersistentClient ensures data survives process restarts.
        """
        try:
            os.makedirs(self._persist_dir, exist_ok=True)
            # PersistentClient stores SQLite + binary index under persist_dir.
            # To switch to an ephemeral in-memory client for testing, set
            # CHROMA_PERSIST_DIR="" and the caller should use chromadb.EphemeralClient.
            self._client = chromadb.PersistentClient(path=self._persist_dir)
            self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=self._ef,
            )
            logger.info(
                f"RAGKnowledgeBase initialized: collection='{self._collection_name}', "
                f"persist_dir='{self._persist_dir}' (persistent)"
            )
        except Exception as e:
            logger.error(
                f"RAGKnowledgeBase init failed — RAG disabled: {e}. "
                f"Check persist_dir='{self._persist_dir}' is writable and "
                f"chromadb/sentence-transformers are properly installed."
            )
            self._available = False

    def add_documents(self, texts: list[str], metadatas: list[dict]) -> int:
        """Add pre-chunked texts to the collection. Returns number added."""
        if not self._available or not texts:
            return 0
        try:
            # Generate deterministic IDs using SHA256 (stable across restarts)
            ids = [
                f"doc_{hashlib.sha256(t.encode()).hexdigest()[:12]}_{i}"
                for i, t in enumerate(texts)
            ]
            self._collection.add(
                documents=texts,
                metadatas=metadatas,
                ids=ids,
            )
            return len(texts)
        except Exception as e:
            logger.warning(f"RAG add_documents failed: {e}")
            return 0

    def add_file(self, filepath: str) -> int:
        """Read file, chunk it, and add to collection. Returns chunk count added."""
        if not self._available:
            return 0
        try:
            text = _read_file(filepath)
            if not text.strip():
                logger.warning(f"RAG: Empty content in file '{filepath}'")
                return 0

            filename = os.path.basename(filepath)
            chunks = _chunk_text(text)
            if not chunks:
                return 0

            metadatas = [
                {"source": filename, "chunk_index": i}
                for i in range(len(chunks))
            ]
            added = self.add_documents(chunks, metadatas)
            logger.info(f"RAG: Added {added} chunks from '{filename}'")
            return added
        except Exception as e:
            logger.warning(f"RAG add_file failed for '{filepath}': {e}")
            return 0

    def query(self, question: str, n_results: int = 3) -> list[str]:
        """Return top-N most relevant document chunks for the question."""
        if not self._available or not question.strip():
            return []
        try:
            count = self.count()
            if count == 0:
                return []
            # Don't request more results than we have
            n = min(n_results, count)
            results = self._collection.query(
                query_texts=[question],
                n_results=n,
            )
            docs = results.get("documents", [[]])[0]
            return [d for d in docs if d]
        except Exception as e:
            logger.warning(f"RAG query failed: {e}")
            return []

    def clear(self) -> None:
        """Delete all documents from the collection."""
        if not self._available:
            return
        try:
            self._client.delete_collection(self._collection_name)
            self._collection = self._client.get_or_create_collection(
                name=self._collection_name,
                embedding_function=self._ef,
            )
            logger.info("RAGKnowledgeBase cleared.")
        except Exception as e:
            logger.warning(f"RAG clear failed: {e}")

    def count(self) -> int:
        """Return total number of documents in the collection."""
        if not self._available:
            return 0
        try:
            return self._collection.count()
        except Exception as e:
            logger.warning(f"RAG count failed: {e}")
            return 0

    @property
    def is_available(self) -> bool:
        return self._available

    def backup(self, backup_dir: Optional[str] = None) -> Optional[str]:
        """Copy ChromaDB persist directory to a timestamped backup.

        Returns the backup path on success, None on failure.
        Default backup location: data/chromadb_backup_YYYYMMDD_HHMMSS/
        """
        import shutil
        from datetime import datetime

        if not os.path.isdir(self._persist_dir):
            logger.warning(f"RAG backup: persist_dir '{self._persist_dir}' does not exist")
            return None

        if backup_dir is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = f"{self._persist_dir}_backup_{ts}"

        try:
            shutil.copytree(self._persist_dir, backup_dir)
            logger.info(f"RAG backup created at '{backup_dir}'")
            return backup_dir
        except Exception as e:
            logger.error(f"RAG backup failed: {e}")
            return None

    def restore(self, backup_dir: str) -> bool:
        """Restore ChromaDB from a backup directory. Requires restart after.

        Returns True on success. The caller should re-instantiate
        RAGKnowledgeBase after restore to pick up the restored data.
        """
        import shutil

        if not os.path.isdir(backup_dir):
            logger.error(f"RAG restore: backup '{backup_dir}' not found")
            return False

        try:
            if os.path.isdir(self._persist_dir):
                shutil.rmtree(self._persist_dir)
            shutil.copytree(backup_dir, self._persist_dir)
            logger.info(f"RAG restored from '{backup_dir}' — restart required")
            return True
        except Exception as e:
            logger.error(f"RAG restore failed: {e}")
            return False
