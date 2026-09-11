"""
Hybrid Multi-Level Caching System (Phase 4 - Module 1)
3-Layer Cache Strategy:
- L1: Redis Hot Cache (frequent access, short TTL)
- L2: Semantic Vector Cache (similarity-based retrieval)
- L3: Fragment Cache (reusable story fragments)
"""
import hashlib
import json
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

class CacheLayer(Enum):
    L1_HOT = "l1_hot"
    L2_SEMANTIC = "l2_semantic"
    L3_FRAGMENT = "l3_fragment"

@dataclass
class CacheEntry:
    key: str
    value: Any
    layer: CacheLayer
    created_at: float = field(default_factory=time.time)
    hits: int = 0
    ttl: int = 3600  # seconds
    
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl

class HybridCacheManager:
    def __init__(self, redis_client=None, embedding_model=None):
        self.l1_cache: Dict[str, CacheEntry] = {}  # In-memory hot cache
        self.l2_cache: Dict[str, List[CacheEntry]] = {}  # Semantic clusters
        self.l3_cache: Dict[str, CacheEntry] = {}  # Fragment cache
        
        self.redis_client = redis_client
        self.embedding_model = embedding_model
        
        # Stats
        self.stats = {
            "l1_hits": 0, "l1_misses": 0,
            "l2_hits": 0, "l2_misses": 0,
            "l3_hits": 0, "l3_misses": 0,
            "total_requests": 0
        }
    
    def _generate_key(self, prompt: str, context_hash: str = "") -> str:
        """Generate deterministic cache key"""
        combined = f"{prompt}:{context_hash}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def _compute_similarity(self, query: str, candidates: List[str]) -> List[Tuple[str, float]]:
        """Compute semantic similarity (mock implementation)"""
        results = []
        for candidate in candidates:
            set1 = set(query.lower().split())
            set2 = set(candidate.lower().split())
            intersection = len(set1 & set2)
            union = len(set1 | set2)
            similarity = intersection / union if union > 0 else 0
            results.append((candidate, similarity))
        return sorted(results, key=lambda x: x[1], reverse=True)
    
    async def get(self, prompt: str, context_hash: str = "", 
                  similarity_threshold: float = 0.85) -> Optional[Any]:
        """Retrieve from cache with 3-layer strategy"""
        self.stats["total_requests"] += 1
        key = self._generate_key(prompt, context_hash)
        
        # Layer 1: Hot Cache (exact match)
        if key in self.l1_cache:
            entry = self.l1_cache[key]
            if not entry.is_expired():
                entry.hits += 1
                self.stats["l1_hits"] += 1
                return entry.value
            else:
                del self.l1_cache[key]
        self.stats["l1_misses"] += 1
        
        # Layer 2: Semantic Cache (similarity match)
        if self.l2_cache:
            candidates = list(self.l2_cache.keys())
            similarities = self._compute_similarity(prompt, candidates)
            
            if similarities and similarities[0][1] >= similarity_threshold:
                best_match_key = similarities[0][0]
                if best_match_key in self.l2_cache and self.l2_cache[best_match_key]:
                    entry = self.l2_cache[best_match_key][0]
                    if not entry.is_expired():
                        entry.hits += 1
                        self.stats["l2_hits"] += 1
                        return entry.value
        self.stats["l2_misses"] += 1
        
        # Layer 3: Fragment Cache (partial matches)
        fragments = self._extract_fragments(prompt)
        for fragment in fragments:
            frag_key = self._generate_key(fragment, "")
            if frag_key in self.l3_cache:
                entry = self.l3_cache[frag_key]
                if not entry.is_expired():
                    entry.hits += 1
                    self.stats["l3_hits"] += 1
                    return entry.value
        self.stats["l3_misses"] += 1
        
        return None
    
    async def set(self, prompt: str, value: Any, context_hash: str = "",
                  layer: CacheLayer = CacheLayer.L1_HOT, ttl: int = 3600):
        """Store value in appropriate cache layer"""
        key = self._generate_key(prompt, context_hash)
        entry = CacheEntry(key=key, value=value, layer=layer, ttl=ttl)
        
        if layer == CacheLayer.L1_HOT:
            self.l1_cache[key] = entry
            self._add_to_semantic_cluster(prompt, entry)
        elif layer == CacheLayer.L2_SEMANTIC:
            self._add_to_semantic_cluster(prompt, entry)
        elif layer == CacheLayer.L3_FRAGMENT:
            fragments = self._extract_fragments(prompt)
            for fragment in fragments:
                frag_key = self._generate_key(fragment, "")
                self.l3_cache[frag_key] = CacheEntry(
                    key=frag_key, value=value, layer=layer, ttl=ttl
                )
    
    def _add_to_semantic_cluster(self, prompt: str, entry: CacheEntry):
        """Add entry to semantic cluster for L2 cache"""
        cluster_key = entry.key[:4]
        if cluster_key not in self.l2_cache:
            self.l2_cache[cluster_key] = []
        self.l2_cache[cluster_key].append(entry)
        if len(self.l2_cache[cluster_key]) > 100:
            self.l2_cache[cluster_key].pop(0)
    
    def _extract_fragments(self, prompt: str) -> List[str]:
        """Extract reusable fragments from prompt"""
        sentences = prompt.split('.')
        fragments = [s.strip() for s in sentences if len(s.strip()) > 20]
        return fragments[:5]
    
    def get_stats(self) -> Dict[str, Any]:
        """Return cache statistics"""
        total = self.stats["total_requests"] or 1
        return {
            "l1_hit_rate": round(self.stats["l1_hits"] / total * 100, 2),
            "l2_hit_rate": round(self.stats["l2_hits"] / total * 100, 2),
            "l3_hit_rate": round(self.stats["l3_hits"] / total * 100, 2),
            "overall_hit_rate": round(
                (self.stats["l1_hits"] + self.stats["l2_hits"] + self.stats["l3_hits"]) / total * 100, 2
            ),
            "total_requests": total,
            "l1_size": len(self.l1_cache),
            "l2_clusters": len(self.l2_cache),
            "l3_size": len(self.l3_cache)
        }
    
    def clear(self, layer: Optional[CacheLayer] = None):
        """Clear cache by layer or all"""
        if layer is None or layer == CacheLayer.L1_HOT:
            self.l1_cache.clear()
        if layer is None or layer == CacheLayer.L2_SEMANTIC:
            self.l2_cache.clear()
        if layer is None or layer == CacheLayer.L3_FRAGMENT:
            self.l3_cache.clear()

if __name__ == "__main__":
    cache = HybridCacheManager()
    print("✓ HybridCacheManager initialized successfully")
