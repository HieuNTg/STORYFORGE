"""StoryContextManager - Quản lý context chia sẻ cho toàn bộ pipeline (Phase 1).

Mục tiêu:
- Giảm 30% latency bằng cách tránh load lại context nhiều lần
- Cung cấp shared context object cho tất cả agents và layers
- Cache thông tin nhân vật, bối cảnh, plot threads
- Hỗ trợ incremental updates thay vì rebuild toàn bộ
"""

import logging
import hashlib
import time
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime
import threading

logger = logging.getLogger(__name__)


@dataclass
class CharacterState:
    """Trạng thái hiện tại của nhân vật."""
    name: str
    physical_state: str = ""  # Vết thương, mệt mỏi, v.v.
    emotional_state: str = ""  # Cảm xúc hiện tại
    knowledge: Set[str] = field(default_factory=set)  # Những gì nhân vật biết
    secrets: Set[str] = field(default_factory=set)  # Bí mật giữ kín
    relationships: Dict[str, str] = field(default_factory=dict)  # Quan hệ với nhân vật khác
    location: str = ""  # Vị trí hiện tại
    goals: List[str] = field(default_factory=list)  # Mục tiêu ngắn hạn
    last_updated_chapter: int = 0
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "physical_state": self.physical_state,
            "emotional_state": self.emotional_state,
            "knowledge": list(self.knowledge),
            "secrets": list(self.secrets),
            "relationships": self.relationships,
            "location": self.location,
            "goals": self.goals,
            "last_updated_chapter": self.last_updated_chapter,
        }


@dataclass
class PlotThread:
    """Một sợi cốt truyện đang diễn ra."""
    thread_id: str
    description: str
    status: str = "open"  # open, resolved, abandoned
    priority: str = "medium"  # low, medium, high, critical
    involved_characters: Set[str] = field(default_factory=set)
    foreshadowing_planted: List[dict] = field(default_factory=list)
    payoff_due_chapter: Optional[int] = None
    last_mentioned_chapter: int = 0
    resolution_hints: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "involved_characters": list(self.involved_characters),
            "foreshadowing_planted": self.foreshadowing_planted,
            "payoff_due_chapter": self.payoff_due_chapter,
            "last_mentioned_chapter": self.last_mentioned_chapter,
            "resolution_hints": self.resolution_hints,
        }


@dataclass
class WorldState:
    """Trạng thái thế giới/bối cảnh."""
    current_location: str = ""
    time_period: str = ""
    weather: str = ""
    active_events: List[str] = field(default_factory=list)  # Sự kiện đang diễn ra
    political_state: str = ""  # Tình hình chính trị
    economic_state: str = ""  # Tình hình kinh tế
    cultural_context: str = ""  # Bối cảnh văn hóa
    magical_rules: List[str] = field(default_factory=list)  # Quy tắc phép thuật (nếu có)
    technology_level: str = ""  # Mức độ công nghệ
    last_updated_chapter: int = 0
    
    def to_dict(self) -> dict:
        return {
            "current_location": self.current_location,
            "time_period": self.time_period,
            "weather": self.weather,
            "active_events": self.active_events,
            "political_state": self.political_state,
            "economic_state": self.economic_state,
            "cultural_context": self.cultural_context,
            "magical_rules": self.magical_rules,
            "technology_level": self.technology_level,
            "last_updated_chapter": self.last_updated_chapter,
        }


@dataclass
class ContextSnapshot:
    """Snapshot của toàn bộ context tại một thời điểm."""
    chapter_number: int
    timestamp: datetime
    character_states: Dict[str, CharacterState]
    plot_threads: Dict[str, PlotThread]
    world_state: WorldState
    thematic_elements: Dict[str, float]  # theme -> intensity (0-1)
    emotional_arc_position: float  # 0-1, vị trí trên cung cảm xúc
    pacing_history: List[str] = field(default_factory=list)  # Lịch sử pacing
    context_hash: str = ""  # Hash để detect changes
    
    def compute_hash(self) -> str:
        """Tính hash của context để phát hiện thay đổi."""
        content = f"{self.chapter_number}:{len(self.character_states)}:{len(self.plot_threads)}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def to_dict(self) -> dict:
        return {
            "chapter_number": self.chapter_number,
            "timestamp": self.timestamp.isoformat(),
            "character_states": {k: v.to_dict() for k, v in self.character_states.items()},
            "plot_threads": {k: v.to_dict() for k, v in self.plot_threads.items()},
            "world_state": self.world_state.to_dict(),
            "thematic_elements": self.thematic_elements,
            "emotional_arc_position": self.emotional_arc_position,
            "pacing_history": self.pacing_history,
            "context_hash": self.context_hash,
        }


class StoryContextManager:
    """Quản lý context chia sẻ cho toàn bộ pipeline.
    
    Usage:
        ctx_manager = StoryContextManager()
        
        # Khởi tạo context từ story draft
        ctx_manager.initialize_from_draft(draft)
        
        # Lấy context cho việc viết chương mới
        ctx = ctx_manager.get_context_for_chapter(5)
        
        # Cập nhật sau khi viết chương
        ctx_manager.update_after_chapter(chapter_content, chapter_number)
        
        # Lấy snapshot cho agents
        snapshot = ctx_manager.get_snapshot(chapter_number=5)
    """
    
    def __init__(self, max_history_size: int = 50):
        self._lock = threading.RLock()
        self.max_history_size = max_history_size
        
        # Core state
        self.character_states: Dict[str, CharacterState] = {}
        self.plot_threads: Dict[str, PlotThread] = {}
        self.world_state = WorldState()
        self.thematic_elements: Dict[str, float] = {}
        
        # History tracking
        self.snapshots: List[ContextSnapshot] = []
        self.change_log: List[dict] = []  # Log các thay đổi quan trọng
        
        # Cache optimization
        self._context_cache: Dict[str, Any] = {}
        self._cache_hits = 0
        self._cache_misses = 0
        self._last_computed_hash = ""
        
        # Metrics
        self.metrics = {
            "initializations": 0,
            "updates": 0,
            "retrievals": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_update_time_ms": 0.0,
        }
    
    def initialize_from_draft(self, draft) -> None:
        """Khởi tạo context từ story draft (sau khi L1 hoàn thành).
        
        Đây là bước quan trọng nhất - extract tất cả thông tin từ draft
        để xây dựng context ban đầu cho L2 và các agents.
        """
        start_time = time.time()
        
        with self._lock:
            logger.info(f"[CONTEXT] Initializing from draft: {draft.title}")
            
            # 1. Extract character states
            if hasattr(draft, 'characters') and draft.characters:
                for char in draft.characters:
                    self.character_states[char.name] = CharacterState(
                        name=char.name,
                        physical_state=getattr(char, 'physical_state', ''),
                        emotional_state=getattr(char, 'initial_emotion', ''),
                        goals=getattr(char, 'goals', []),
                        relationships=getattr(char, 'relationships', {}),
                        last_updated_chapter=0,
                    )
                    logger.debug(f"  - Initialized character: {char.name}")
            
            # 2. Extract plot threads từ outline
            if hasattr(draft, 'outline') and draft.outline:
                thread_id = 0
                for chapter_outline in draft.outline:
                    if hasattr(chapter_outline, 'main_conflict'):
                        thread_id += 1
                        self.plot_threads[f"thread_{thread_id}"] = PlotThread(
                            thread_id=f"thread_{thread_id}",
                            description=chapter_outline.main_conflict,
                            status="open",
                            priority="medium",
                            last_mentioned_chapter=chapter_outline.chapter_number,
                        )
            
            # 3. Initialize world state
            if hasattr(draft, 'world'):
                self.world_state = WorldState(
                    current_location=getattr(draft.world, 'primary_location', ''),
                    time_period=getattr(draft.world, 'time_period', ''),
                    cultural_context=getattr(draft.world, 'cultural_context', ''),
                    last_updated_chapter=0,
                )
            
            # 4. Extract thematic elements
            if hasattr(draft, 'themes') and draft.themes:
                for theme in draft.themes:
                    self.thematic_elements[theme] = 0.5  # Default intensity
            
            # 5. Create initial snapshot
            initial_snapshot = ContextSnapshot(
                chapter_number=0,
                timestamp=datetime.now(),
                character_states=self.character_states.copy(),
                plot_threads=self.plot_threads.copy(),
                world_state=self.world_state,
                thematic_elements=self.thematic_elements.copy(),
                emotional_arc_position=0.0,
            )
            initial_snapshot.context_hash = initial_snapshot.compute_hash()
            self.snapshots.append(initial_snapshot)
            self._last_computed_hash = initial_snapshot.context_hash
            
            self.metrics["initializations"] += 1
            elapsed = (time.time() - start_time) * 1000
            self.metrics["avg_update_time_ms"] = elapsed
            
            logger.info(f"[CONTEXT] Initialization complete in {elapsed:.1f}ms")
            logger.info(f"  - Characters: {len(self.character_states)}")
            logger.info(f"  - Plot threads: {len(self.plot_threads)}")
            logger.info(f"  - Themes: {len(self.thematic_elements)}")
    
    def get_context_for_chapter(self, chapter_number: int) -> dict:
        """Lấy context cần thiết để viết/chương chapter_number.
        
        Trả về dictionary optimized cho LLM prompts.
        """
        cache_key = f"chapter_{chapter_number}"
        
        # Check cache first
        if cache_key in self._context_cache:
            self._cache_hits += 1
            self.metrics["cache_hits"] += 1
            logger.debug(f"[CONTEXT] Cache hit for {cache_key}")
            return self._context_cache[cache_key]
        
        self._cache_misses += 1
        self.metrics["cache_misses"] += 1
        
        with self._lock:
            # Find most recent snapshot before this chapter
            relevant_snapshot = None
            for snapshot in reversed(self.snapshots):
                if snapshot.chapter_number < chapter_number:
                    relevant_snapshot = snapshot
                    break
            
            if relevant_snapshot is None:
                relevant_snapshot = self.snapshots[0] if self.snapshots else None
            
            # Build optimized context dict
            context = {
                "chapter_number": chapter_number,
                "characters": {},
                "open_threads": [],
                "world_state": {},
                "themes": {},
                "recent_changes": [],
            }
            
            if relevant_snapshot:
                # Only include active characters
                for name, state in relevant_snapshot.character_states.items():
                    context["characters"][name] = {
                        "current_state": state.to_dict(),
                        "is_active": state.last_updated_chapter >= chapter_number - 3,
                    }
                
                # Only include open/active threads
                for thread_id, thread in relevant_snapshot.plot_threads.items():
                    if thread.status == "open":
                        context["open_threads"].append(thread.to_dict())
                
                context["world_state"] = relevant_snapshot.world_state.to_dict()
                context["themes"] = relevant_snapshot.thematic_elements.copy()
                
                # Add recent changes from change_log
                recent_changes = [
                    change for change in self.change_log
                    if change.get("chapter", 0) >= chapter_number - 2
                ]
                context["recent_changes"] = recent_changes[-5:]  # Last 5 changes
            
            # Cache the result
            self._context_cache[cache_key] = context
            
            # Limit cache size
            if len(self._context_cache) > 100:
                oldest_key = next(iter(self._context_cache))
                del self._context_cache[oldest_key]
            
            self.metrics["retrievals"] += 1
            return context
    
    def update_after_chapter(self, chapter_content: str, chapter_number: int) -> None:
        """Cập nhật context sau khi viết xong một chương.
        
        Phân tích chapter content để extract:
        - Character state changes
        - New plot threads
        - Thread resolutions
        - World state changes
        - Thematic developments
        """
        start_time = time.time()
        
        with self._lock:
            logger.info(f"[CONTEXT] Updating after chapter {chapter_number}")
            
            changes_made = []
            
            # Note: Actual extraction would use NLP/LLM here
            # For now, we'll mark this as a placeholder for future enhancement
            # In Phase 2, we'll add semantic analysis to auto-extract changes
            
            # Create new snapshot
            new_snapshot = ContextSnapshot(
                chapter_number=chapter_number,
                timestamp=datetime.now(),
                character_states={k: v for k, v in self.character_states.items()},
                plot_threads={k: v for k, v in self.plot_threads.items()},
                world_state=self.world_state,
                thematic_elements=self.thematic_elements.copy(),
                emotional_arc_position=self._calculate_emotional_arc(chapter_number),
                pacing_history=self._get_pacing_history(chapter_number),
            )
            new_snapshot.context_hash = new_snapshot.compute_hash()
            
            # Detect if context actually changed
            if new_snapshot.context_hash != self._last_computed_hash:
                self.snapshots.append(new_snapshot)
                self._last_computed_hash = new_snapshot.context_hash
                
                # Log the change
                changes_made.append({
                    "chapter": chapter_number,
                    "timestamp": datetime.now().isoformat(),
                    "type": "context_update",
                    "hash": new_snapshot.context_hash,
                })
                self.change_log.extend(changes_made)
                
                # Trim history if needed
                if len(self.snapshots) > self.max_history_size:
                    self.snapshots = self.snapshots[-self.max_history_size:]
                
                if len(self.change_log) > 200:
                    self.change_log = self.change_log[-200:]
                
                # Invalidate cache for future chapters
                keys_to_invalidate = [
                    k for k in self._context_cache.keys()
                    if k.startswith("chapter_") and 
                    int(k.split("_")[1]) > chapter_number
                ]
                for key in keys_to_invalidate:
                    del self._context_cache[key]
            
            self.metrics["updates"] += 1
            elapsed = (time.time() - start_time) * 1000
            
            # Update running average
            old_avg = self.metrics["avg_update_time_ms"]
            n = self.metrics["updates"]
            self.metrics["avg_update_time_ms"] = ((old_avg * (n - 1)) + elapsed) / n
            
            logger.info(f"[CONTEXT] Update complete in {elapsed:.1f}ms")
            logger.info(f"  - Changes detected: {len(changes_made)}")
            logger.info(f"  - Total snapshots: {len(self.snapshots)}")
    
    def get_snapshot(self, chapter_number: int) -> Optional[ContextSnapshot]:
        """Lấy snapshot tại một chương cụ thể."""
        with self._lock:
            for snapshot in self.snapshots:
                if snapshot.chapter_number == chapter_number:
                    return snapshot
            
            # If exact match not found, return closest previous
            for snapshot in reversed(self.snapshots):
                if snapshot.chapter_number < chapter_number:
                    return snapshot
            
            return self.snapshots[0] if self.snapshots else None
    
    def _calculate_emotional_arc(self, chapter_number: int) -> float:
        """Tính toán vị trí trên cung cảm xúc (0-1).
        
        Simple heuristic based on chapter position.
        Will be enhanced in Phase 2 with actual sentiment analysis.
        """
        total_chapters = len(self.snapshots) if self.snapshots else 10
        position = chapter_number / total_chapters
        
        # Classic three-act structure emotional arc
        if position < 0.25:
            return 0.3 + (position * 0.4)  # Rising action
        elif position < 0.5:
            return 0.4 + ((position - 0.25) * 0.2)  # Building tension
        elif position < 0.75:
            return 0.45 - ((position - 0.5) * 0.3)  # Crisis/dark moment
        else:
            return 0.375 + ((position - 0.75) * 0.625)  # Resolution
    
    def _get_pacing_history(self, chapter_number: int) -> List[str]:
        """Lấy lịch sử pacing cho các chương gần đây."""
        # Placeholder - will be enhanced with actual pacing analysis
        recent_pacing = []
        for i in range(max(0, chapter_number - 5), chapter_number):
            # Simple heuristic based on chapter position
            if i % 3 == 0:
                recent_pacing.append("fast")
            elif i % 3 == 1:
                recent_pacing.append("medium")
            else:
                recent_pacing.append("slow")
        return recent_pacing
    
    def log_change(self, change_type: str, details: dict, chapter: int) -> None:
        """Log một thay đổi quan trọng trong context."""
        with self._lock:
            change_record = {
                "chapter": chapter,
                "timestamp": datetime.now().isoformat(),
                "type": change_type,
                "details": details,
            }
            self.change_log.append(change_record)
            
            if len(self.change_log) > 200:
                self.change_log = self.change_log[-200:]
            
            logger.debug(f"[CONTEXT] Logged change: {change_type} at chapter {chapter}")
    
    def get_metrics(self) -> dict:
        """Lấy metrics về hiệu năng context management."""
        with self._lock:
            cache_total = self._cache_hits + self._cache_misses
            hit_rate = (self._cache_hits / cache_total * 100) if cache_total > 0 else 0
            
            return {
                **self.metrics,
                "cache_hit_rate_percent": round(hit_rate, 2),
                "total_snapshots": len(self.snapshots),
                "total_changes_logged": len(self.change_log),
                "unique_characters": len(self.character_states),
                "active_threads": len([t for t in self.plot_threads.values() if t.status == "open"]),
            }
    
    def clear_cache(self) -> None:
        """Xóa cache để giải phóng memory."""
        with self._lock:
            self._context_cache.clear()
            logger.info("[CONTEXT] Cache cleared")
    
    def export_context_summary(self) -> dict:
        """Export tóm tắt context để debug hoặc lưu trữ."""
        with self._lock:
            return {
                "timestamp": datetime.now().isoformat(),
                "metrics": self.get_metrics(),
                "latest_snapshot": self.snapshots[-1].to_dict() if self.snapshots else None,
                "recent_changes": self.change_log[-10:],
            }


# Singleton instance for global access (optional)
_global_context_manager: Optional[StoryContextManager] = None
_global_context_lock = threading.Lock()


def get_global_context_manager() -> StoryContextManager:
    """Lấy global context manager singleton."""
    global _global_context_manager
    if _global_context_manager is None:
        with _global_context_lock:
            if _global_context_manager is None:
                _global_context_manager = StoryContextManager()
    return _global_context_manager


def reset_global_context_manager() -> None:
    """Reset global context manager (cho testing hoặc new story)."""
    global _global_context_manager
    with _global_context_lock:
        _global_context_manager = None
        logger.info("[CONTEXT] Global context manager reset")
