"""
Dynamic Context Window Management (Phase 4 - Module 2)
Core + Sliding Window + RAG Retrieval Strategy:
- Core Context: Fixed story metadata, characters, world-building
- Sliding Window: Last 3 chapters for immediate context
- RAG Retrieval: Vector DB lookup for specific details on-demand
"""
import hashlib
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

class ContextType(Enum):
    CORE = "core"
    SLIDING = "sliding"
    RAG = "rag"

@dataclass
class ContextChunk:
    chapter_id: str
    content: str
    embeddings: Optional[List[float]] = None
    created_at: float = field(default_factory=time.time)
    access_count: int = 0

class DynamicContextEngine:
    def __init__(self, vector_db=None, embedding_model=None, max_sliding_window: int = 3):
        self.core_context: Dict[str, Any] = {}
        self.sliding_window: List[ContextChunk] = []
        self.vector_db = vector_db
        self.embedding_model = embedding_model
        self.max_sliding_window = max_sliding_window
        
        # Stats
        self.stats = {
            "core_access": 0,
            "sliding_access": 0,
            "rag_queries": 0,
            "cache_hits": 0,
            "total_requests": 0
        }
    
    def set_core_context(self, story_id: str, metadata: Dict[str, Any],
                         characters: List[Dict], world_building: Dict):
        """Set immutable core context"""
        self.core_context = {
            "story_id": story_id,
            "metadata": metadata,
            "characters": {char["name"]: char for char in characters},
            "world_building": world_building,
            "created_at": time.time()
        }
    
    def add_chapter_to_sliding_window(self, chapter_id: str, content: str):
        """Add chapter to sliding window, evict oldest if needed"""
        chunk = ContextChunk(chapter_id=chapter_id, content=content)
        self.sliding_window.append(chunk)
        
        # Evict oldest if exceeds max size
        while len(self.sliding_window) > self.max_sliding_window:
            self.sliding_window.pop(0)
    
    async def get_context(self, query: str, 
                          include_sliding: bool = True,
                          similarity_threshold: float = 0.75) -> Dict[str, Any]:
        """
        Retrieve context using hybrid strategy:
        1. Always include core context
        2. Include sliding window chapters
        3. RAG retrieval for specific queries
        """
        self.stats["total_requests"] += 1
        result = {
            "core": self.core_context,
            "sliding_chapters": [],
            "rag_results": [],
            "query": query
        }
        
        # Add sliding window
        if include_sliding and self.sliding_window:
            result["sliding_chapters"] = [
                {"chapter_id": ch.chapter_id, "content": ch.content}
                for ch in self.sliding_window
            ]
            self.stats["sliding_access"] += 1
        
        # RAG retrieval for specific entities/queries
        if self.vector_db and query:
            rag_results = await self._retrieve_from_vector_db(query, similarity_threshold)
            if rag_results:
                result["rag_results"] = rag_results
                self.stats["rag_queries"] += 1
                self.stats["cache_hits"] += len(rag_results)
        
        return result
    
    async def _retrieve_from_vector_db(self, query: str, 
                                       threshold: float) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks from vector DB"""
        if not self.vector_db:
            return []
        
        # Generate query embedding (mock)
        query_embedding = self._generate_embedding(query)
        
        # Search vector DB
        results = await self.vector_db.search(
            query_embedding=query_embedding,
            threshold=threshold,
            top_k=5
        )
        
        return results
    
    def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding vector (mock implementation)"""
        if self.embedding_model:
            return self.embedding_model.encode(text).tolist()
        
        # Fallback: simple hash-based pseudo-embedding
        hash_val = hashlib.md5(text.encode()).hexdigest()
        return [float(ord(c)) / 256.0 for c in hash_val[:32]]
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Return context summary for debugging"""
        return {
            "core_context_keys": list(self.core_context.keys()),
            "sliding_window_size": len(self.sliding_window),
            "sliding_chapter_ids": [ch.chapter_id for ch in self.sliding_window],
            "stats": self.stats
        }
    
    def clear_sliding_window(self):
        """Clear sliding window (useful for story reset)"""
        self.sliding_window.clear()
    
    def update_core_metadata(self, updates: Dict[str, Any]):
        """Update specific core context fields"""
        for key, value in updates.items():
            if key in self.core_context:
                self.core_context[key] = value

if __name__ == "__main__":
    engine = DynamicContextEngine()
    print("✓ DynamicContextEngine initialized successfully")
