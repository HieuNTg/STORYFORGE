"""Thread Watchdog — đảm bảo các tuyến truyện được giải quyết đúng cách.

Tracks: open threads from L1, monitors resolution, flags forgotten threads.
Prevents: dangling plot threads, premature resolution, inconsistent closure.
"""

import logging
from pydantic import BaseModel, Field
from services.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _get_stale_threshold() -> int:
    """Get thread stale threshold from config."""
    try:
        from config import ConfigManager
        return getattr(ConfigManager().pipeline, "thread_stale_threshold", 3)
    except Exception:
        return 3


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
        from pipeline.layer2_enhance import _envelope_access as _env
        open_threads_raw = _env.open_threads(draft)
        resolved_threads_raw = _env.resolved_threads(draft)

        def _as_dict(t):
            if isinstance(t, dict):
                return t
            if hasattr(t, "model_dump"):
                d = t.model_dump()
                # Project envelope ThreadEntry shape to legacy dict keys.
                return {
                    "thread_id": d.get("id") or d.get("thread_id"),
                    "description": d.get("label") or d.get("description") or "",
                    "introduced_chapter": d.get("opened_chapter") or d.get("introduced_chapter") or 1,
                    "resolution_chapter": d.get("expected_close_chapter") or d.get("resolution_chapter"),
                    "characters": d.get("characters") or [],
                    "importance": d.get("importance") or "normal",
                }
            return None

        for t in open_threads_raw:
            d = _as_dict(t)
            if d is not None:
                tid = d.get("thread_id") or self._gen_thread_id()
                self.threads[tid] = PlotThread(
                    thread_id=tid,
                    description=d.get("description", str(t)),
                    introduced_chapter=d.get("introduced_chapter", 1),
                    expected_resolution_chapter=d.get("resolution_chapter"),
                    characters_involved=d.get("characters", []),
                    importance=d.get("importance", "normal"),
                    status="open",
                )
            elif isinstance(t, str):
                tid = self._gen_thread_id()
                self.threads[tid] = PlotThread(
                    thread_id=tid,
                    description=t,
                    status="open",
                )

        for t in resolved_threads_raw:
            d = _as_dict(t)
            if d is not None:
                tid = d.get("thread_id") or self._gen_thread_id()
                self.threads[tid] = PlotThread(
                    thread_id=tid,
                    description=d.get("description", str(t)),
                    status="resolved",
                    actual_resolution_chapter=d.get("resolution_chapter"),
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
            stale_threshold = _get_stale_threshold()
            if t.last_mentioned_chapter > 0 and chapter_number - t.last_mentioned_chapter > stale_threshold:
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


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6: Thread Resolution Enforcement
# ══════════════════════════════════════════════════════════════════════════════


class ThreadResolutionEnforcer:
    """Force resolution of open threads near story end.

    Works with ThreadWatchdog to ensure all threads are properly closed.
    """

    FORCE_RESOLUTION_PROMPT = """Bạn là editor chuyên đảm bảo tuyến truyện được giải quyết.

Chương hiện tại: {chapter_number}/{total_chapters}
Nội dung chương đã enhance:
{content}

CÁC TUYẾN TRUYỆN BẮT BUỘC PHẢI GIẢI QUYẾT TRONG CHƯƠNG NÀY:
{threads_to_resolve}

NHIỆM VỤ:
1. Thêm đoạn văn giải quyết từng tuyến truyện nếu chưa có
2. Giữ nguyên nội dung gốc, chỉ THÊM không XÓA
3. Mỗi tuyến cần ít nhất 1-2 câu xác nhận kết thúc

Trả về JSON:
{{
  "resolutions_added": [
    {{
      "thread_description": "mô tả tuyến",
      "resolution_text": "đoạn văn giải quyết (2-4 câu)",
      "insert_after": "câu cuối của đoạn nào để chèn vào sau"
    }}
  ],
  "all_resolved": true/false
}}"""

    def __init__(self, watchdog: ThreadWatchdog):
        self.watchdog = watchdog
        self.llm = LLMClient()
        self.resolutions_applied: list[dict] = []

    def get_threads_requiring_resolution(
        self,
        chapter_number: int,
        total_chapters: int,
    ) -> list[PlotThread]:
        """Get threads that MUST be resolved in this chapter."""
        must_resolve = []

        for t in self.watchdog.threads.values():
            if t.status == "resolved":
                continue

            # Deadline is this chapter
            if t.expected_resolution_chapter == chapter_number:
                must_resolve.append(t)
                continue

            # Critical thread in final 2 chapters
            if chapter_number >= total_chapters - 1 and t.importance == "critical":
                must_resolve.append(t)
                continue

            # Last chapter — ALL open threads
            if chapter_number == total_chapters and t.status in ("open", "progressing"):
                must_resolve.append(t)
                continue

            # Severely overdue (5+ chapters past deadline)
            if t.expected_resolution_chapter and chapter_number > t.expected_resolution_chapter + 5:
                must_resolve.append(t)

        return must_resolve

    def format_enforcement_prompt(
        self,
        chapter_number: int,
        total_chapters: int,
    ) -> str:
        """Format prompt block for mandatory thread resolution."""
        must_resolve = self.get_threads_requiring_resolution(chapter_number, total_chapters)
        if not must_resolve:
            return ""

        lines = ["## 🚨 BẮT BUỘC: GIẢI QUYẾT CÁC TUYẾN TRUYỆN SAU"]
        lines.append("Chương này PHẢI đóng các tuyến truyện này. KHÔNG ĐƯỢC bỏ qua.")
        lines.append("")

        for t in must_resolve:
            reason = ""
            if t.expected_resolution_chapter == chapter_number:
                reason = "đến deadline"
            elif chapter_number == total_chapters:
                reason = "chương cuối"
            elif t.importance == "critical":
                reason = "critical thread"
            else:
                reason = "quá hạn"

            lines.append(f"- **{t.description}** [{reason}]")
            if t.characters_involved:
                lines.append(f"  Nhân vật: {', '.join(t.characters_involved[:3])}")

        lines.append("")
        lines.append("Mỗi tuyến cần được giải quyết RÕRÀNG trong văn bản (không ngầm định).")

        return "\n".join(lines)

    def force_resolution(
        self,
        enhanced_content: str,
        chapter_number: int,
        total_chapters: int,
    ) -> tuple[str, list[dict]]:
        """Force resolution of pending threads by adding resolution text.

        Returns (modified_content, resolutions_added).
        """
        must_resolve = self.get_threads_requiring_resolution(chapter_number, total_chapters)
        if not must_resolve:
            return enhanced_content, []

        # Check which threads are already resolved in content
        unresolved = []
        for t in must_resolve:
            keywords = t.description.lower().split()[:5]
            keywords = [kw for kw in keywords if len(kw) > 3]
            if not keywords:
                unresolved.append(t)
                continue

            mentioned = any(kw in enhanced_content.lower() for kw in keywords)
            if not mentioned:
                unresolved.append(t)

        if not unresolved:
            # All threads appear resolved
            return enhanced_content, []

        # Use LLM to generate resolution text
        threads_text = "\n".join(
            f"- {t.description} (nhân vật: {', '.join(t.characters_involved[:2]) or 'chưa rõ'})"
            for t in unresolved
        )

        try:
            result = self.llm.generate_json(
                system_prompt="Bạn là editor chuyên giải quyết tuyến truyện. Trả về JSON.",
                user_prompt=self.FORCE_RESOLUTION_PROMPT.format(
                    chapter_number=chapter_number,
                    total_chapters=total_chapters,
                    content=enhanced_content[-3000:],  # Use end of chapter
                    threads_to_resolve=threads_text,
                ),
                temperature=0.7,
                max_tokens=1000,
            )

            resolutions = result.get("resolutions_added", [])
            modified_content = enhanced_content

            for res in resolutions:
                resolution_text = res.get("resolution_text", "")
                if not resolution_text:
                    continue

                # Append resolution near the end (before final paragraph)
                paragraphs = modified_content.rsplit("\n\n", 1)
                if len(paragraphs) == 2:
                    modified_content = f"{paragraphs[0]}\n\n{resolution_text}\n\n{paragraphs[1]}"
                else:
                    modified_content = f"{modified_content}\n\n{resolution_text}"

                self.resolutions_applied.append({
                    "thread": res.get("thread_description", ""),
                    "chapter": chapter_number,
                    "text_added": resolution_text[:100],
                })

                # Mark thread as resolved
                for t in unresolved:
                    if t.description[:30].lower() in res.get("thread_description", "").lower():
                        t.status = "resolved"
                        t.actual_resolution_chapter = chapter_number
                        t.resolution_notes = "Force-resolved by ThreadResolutionEnforcer"
                        break

            logger.info(
                f"[ThreadEnforcer] Ch{chapter_number}: force-resolved {len(resolutions)} threads"
            )
            return modified_content, resolutions

        except Exception as e:
            logger.warning(f"Thread force resolution failed: {e}")
            return enhanced_content, []

    def get_enforcement_summary(self) -> dict:
        """Get summary of enforcement actions taken."""
        unresolved = [
            t for t in self.watchdog.threads.values()
            if t.status not in ("resolved",)
        ]

        return {
            "total_threads": len(self.watchdog.threads),
            "resolved": len(self.watchdog.threads) - len(unresolved),
            "unresolved": len(unresolved),
            "force_resolved": len(self.resolutions_applied),
            "resolution_rate": (
                (len(self.watchdog.threads) - len(unresolved)) / len(self.watchdog.threads)
                if self.watchdog.threads else 1.0
            ),
            "unresolved_threads": [
                {"id": t.thread_id, "desc": t.description[:50], "importance": t.importance}
                for t in unresolved[:5]
            ],
        }


def should_enforce_resolution(chapter_number: int, total_chapters: int) -> bool:
    """Determine if resolution enforcement should be applied."""
    # Enforce in final 3 chapters or last 15% of story
    if chapter_number >= total_chapters - 2:
        return True
    if total_chapters > 10 and chapter_number / total_chapters >= 0.85:
        return True
    return False
