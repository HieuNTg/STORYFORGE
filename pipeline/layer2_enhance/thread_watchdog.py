"""Thread Watchdog — đảm bảo các tuyến truyện được giải quyết đúng cách.

Tracks: open threads from L1, monitors resolution, flags forgotten threads.
Prevents: dangling plot threads, premature resolution, inconsistent closure.
"""

import logging
from pydantic import BaseModel, Field
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class PlotThread(BaseModel):
    """Một tuyến truyện cần theo dõi."""
    thread_id: str
    description: str
    introduced_chapter: int = 1
    expected_resolution_chapter: int | None = None  # From L1 planning
    actual_resolution_chapter: int | None = None
    status: str = "open"  # open | progressing | resolved | abandoned
    characters_involved: list[str] = Field(default_factory=list)
    importance: str = "normal"  # critical | normal | minor
    last_mentioned_chapter: int = 0
    resolution_notes: str = ""


class ThreadWatchdog:
    """Theo dõi và đảm bảo tuyến truyện được xử lý đúng."""

    CHECK_THREAD_STATUS_PROMPT = """Phân tích xem nội dung chương có đề cập/tiến triển các tuyến truyện không.

Các tuyến truyện đang mở:
{threads_text}

Nội dung chương {chapter_number}:
{content}

Trả về JSON:
{{
  "thread_updates": [
    {{
      "thread_id": "id",
      "mentioned": true/false,
      "status_change": "progressing" | "resolved" | null,
      "resolution_notes": "ghi chú nếu resolved"
    }}
  ],
  "new_threads": [
    {{
      "description": "mô tả tuyến mới",
      "characters": ["nhân vật liên quan"],
      "importance": "critical" | "normal" | "minor"
    }}
  ]
}}"""

    def __init__(self):
        self.threads: dict[str, PlotThread] = {}
        self.llm = LLMClient()
        self._thread_counter = 0

    def _gen_thread_id(self) -> str:
        self._thread_counter += 1
        return f"thread_{self._thread_counter}"

    def load_from_draft(self, draft) -> "ThreadWatchdog":
        """Load threads từ L1 draft (open_threads, resolved_threads)."""
        open_threads = getattr(draft, "open_threads", []) or []
        resolved_threads = getattr(draft, "resolved_threads", []) or []

        for t in open_threads:
            if isinstance(t, dict):
                tid = t.get("thread_id") or self._gen_thread_id()
                self.threads[tid] = PlotThread(
                    thread_id=tid,
                    description=t.get("description", str(t)),
                    introduced_chapter=t.get("introduced_chapter", 1),
                    expected_resolution_chapter=t.get("resolution_chapter"),
                    characters_involved=t.get("characters", []),
                    importance=t.get("importance", "normal"),
                    status="open",
                )
            elif isinstance(t, str):
                tid = self._gen_thread_id()
                self.threads[tid] = PlotThread(
                    thread_id=tid,
                    description=t,
                    status="open",
                )

        for t in resolved_threads:
            if isinstance(t, dict):
                tid = t.get("thread_id") or self._gen_thread_id()
                self.threads[tid] = PlotThread(
                    thread_id=tid,
                    description=t.get("description", str(t)),
                    status="resolved",
                    actual_resolution_chapter=t.get("resolution_chapter"),
                )
            elif isinstance(t, str):
                tid = self._gen_thread_id()
                self.threads[tid] = PlotThread(
                    thread_id=tid,
                    description=t,
                    status="resolved",
                )

        logger.info(f"ThreadWatchdog: loaded {len(self.threads)} threads")
        return self

    def add_thread(
        self,
        description: str,
        introduced_chapter: int,
        characters: list[str] = None,
        importance: str = "normal",
        expected_resolution: int | None = None,
    ) -> str:
        """Thêm thread mới."""
        tid = self._gen_thread_id()
        self.threads[tid] = PlotThread(
            thread_id=tid,
            description=description,
            introduced_chapter=introduced_chapter,
            expected_resolution_chapter=expected_resolution,
            characters_involved=characters or [],
            importance=importance,
            status="open",
        )
        return tid

    def get_open_threads(self) -> list[PlotThread]:
        """Lấy danh sách threads đang mở."""
        return [t for t in self.threads.values() if t.status in ("open", "progressing")]

    def get_threads_for_chapter(self, chapter_number: int, total_chapters: int) -> list[PlotThread]:
        """Lấy threads cần được chú ý trong chương này."""
        open_threads = self.get_open_threads()
        relevant = []

        for t in open_threads:
            # Thread should be resolved by expected chapter
            if t.expected_resolution_chapter and t.expected_resolution_chapter == chapter_number:
                t.importance = "critical"  # Escalate importance
                relevant.append(t)
                continue

            # Thread hasn't been mentioned in a while (stale)
            if t.last_mentioned_chapter > 0 and chapter_number - t.last_mentioned_chapter > 3:
                relevant.append(t)
                continue

            # Near end of story, critical threads must resolve
            if chapter_number >= total_chapters - 2 and t.importance == "critical":
                relevant.append(t)
                continue

            # Normal inclusion
            relevant.append(t)

        return relevant

    def check_chapter(
        self,
        chapter_content: str,
        chapter_number: int,
    ) -> dict:
        """Kiểm tra chapter và cập nhật trạng thái threads."""
        open_threads = self.get_open_threads()
        if not open_threads:
            return {"updates": [], "new_threads": [], "warnings": []}

        threads_text = "\n".join(
            f"- [{t.thread_id}] {t.description} (từ ch{t.introduced_chapter}, {t.importance})"
            for t in open_threads[:10]
        )

        try:
            result = self.llm.generate_json(
                system_prompt="Phân tích tiến triển tuyến truyện. Trả về JSON.",
                user_prompt=self.CHECK_THREAD_STATUS_PROMPT.format(
                    threads_text=threads_text,
                    chapter_number=chapter_number,
                    content=chapter_content[:4000],
                ),
                temperature=0.1,
                max_tokens=600,
                model_tier="cheap",
            )

            updates = []
            warnings = []

            # Process thread updates
            for update in result.get("thread_updates", []):
                tid = update.get("thread_id", "")
                if tid not in self.threads:
                    continue

                thread = self.threads[tid]

                if update.get("mentioned"):
                    thread.last_mentioned_chapter = chapter_number

                status_change = update.get("status_change")
                if status_change == "resolved":
                    thread.status = "resolved"
                    thread.actual_resolution_chapter = chapter_number
                    thread.resolution_notes = update.get("resolution_notes", "")
                    updates.append({
                        "thread_id": tid,
                        "action": "resolved",
                        "chapter": chapter_number,
                    })
                elif status_change == "progressing":
                    thread.status = "progressing"
                    updates.append({
                        "thread_id": tid,
                        "action": "progressed",
                        "chapter": chapter_number,
                    })

            # Add new threads discovered
            for new_t in result.get("new_threads", []):
                desc = new_t.get("description", "")
                if desc:
                    new_tid = self.add_thread(
                        description=desc,
                        introduced_chapter=chapter_number,
                        characters=new_t.get("characters", []),
                        importance=new_t.get("importance", "normal"),
                    )
                    updates.append({
                        "thread_id": new_tid,
                        "action": "discovered",
                        "chapter": chapter_number,
                    })

            # Check for stale critical threads
            for t in open_threads:
                if t.importance == "critical" and t.last_mentioned_chapter > 0:
                    gap = chapter_number - t.last_mentioned_chapter
                    if gap >= 3:
                        warnings.append({
                            "thread_id": t.thread_id,
                            "type": "stale_critical",
                            "message": f"Critical thread '{t.description[:50]}' không được đề cập trong {gap} chương",
                        })

            return {"updates": updates, "new_threads": [], "warnings": warnings}

        except Exception as e:
            logger.warning(f"Thread check failed for ch{chapter_number}: {e}")
            return {"updates": [], "new_threads": [], "warnings": []}

    def format_constraints_for_chapter(self, chapter_number: int, total_chapters: int) -> str:
        """Tạo text ràng buộc threads cho enhance prompt."""
        relevant = self.get_threads_for_chapter(chapter_number, total_chapters)
        if not relevant:
            return ""

        lines = ["## Tuyến truyện cần xử lý"]

        # Critical/must-resolve threads
        critical = [t for t in relevant if t.importance == "critical"]
        if critical:
            lines.append("**[CRITICAL - Phải giải quyết]:**")
            for t in critical:
                expected = f" (deadline: ch{t.expected_resolution_chapter})" if t.expected_resolution_chapter else ""
                lines.append(f"  - {t.description}{expected}")

        # Normal open threads
        normal = [t for t in relevant if t.importance != "critical"]
        if normal:
            lines.append("**[Đang mở - Cần tiến triển]:**")
            for t in normal[:5]:
                stale = " ⚠️ STALE" if (t.last_mentioned_chapter and chapter_number - t.last_mentioned_chapter > 2) else ""
                lines.append(f"  - {t.description}{stale}")

        # Final chapter warning
        if chapter_number == total_chapters:
            open_count = len(self.get_open_threads())
            if open_count > 0:
                lines.append(f"\n**⚠️ CHƯƠNG CUỐI: Còn {open_count} tuyến chưa giải quyết!**")

        return "\n".join(lines)

    def get_unresolved_report(self, total_chapters: int) -> list[dict]:
        """Báo cáo threads chưa được giải quyết sau khi kết thúc."""
        unresolved = []
        for t in self.threads.values():
            if t.status not in ("resolved",):
                unresolved.append({
                    "thread_id": t.thread_id,
                    "description": t.description,
                    "introduced_chapter": t.introduced_chapter,
                    "expected_resolution": t.expected_resolution_chapter,
                    "importance": t.importance,
                    "last_mentioned": t.last_mentioned_chapter,
                })
        return unresolved

    def validate_enhanced_chapter(
        self,
        enhanced_content: str,
        chapter_number: int,
        total_chapters: int,
    ) -> list[dict]:
        """Validate enhanced chapter cho thread consistency."""
        violations = []

        # Check if critical threads at deadline are resolved
        for t in self.threads.values():
            if t.status == "resolved":
                continue

            if t.expected_resolution_chapter == chapter_number and t.importance == "critical":
                # Check if content resolves this thread
                keywords = t.description.lower().split()[:5]
                mentioned = any(kw in enhanced_content.lower() for kw in keywords if len(kw) > 3)
                if not mentioned:
                    violations.append({
                        "type": "missed_resolution",
                        "thread_id": t.thread_id,
                        "chapter": chapter_number,
                        "description": f"Critical thread '{t.description[:50]}' should resolve in ch{chapter_number} but not mentioned",
                        "severity": "critical",
                    })

        # Final chapter: all critical threads should be resolved
        if chapter_number == total_chapters:
            for t in self.threads.values():
                if t.status != "resolved" and t.importance == "critical":
                    violations.append({
                        "type": "unresolved_critical",
                        "thread_id": t.thread_id,
                        "chapter": chapter_number,
                        "description": f"Critical thread '{t.description[:50]}' unresolved at story end",
                        "severity": "critical",
                    })

        return violations
