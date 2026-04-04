"""Story Bible Manager — bộ nhớ dài hạn cho truyện 100+ chương."""

import logging
import uuid
from models.schemas import (
    StoryBible, PlotThread, StoryArc, StoryDraft,
    Chapter, CharacterState, PlotEvent,
)

logger = logging.getLogger(__name__)


class StoryBibleManager:
    """Quản lý Story Bible — cập nhật sau mỗi chương để đảm bảo tính liên tục."""

    def initialize(self, draft: StoryDraft, arc_size: int = 30) -> StoryBible:
        """Tạo bible ban đầu từ thiết lập truyện."""
        bible = StoryBible(
            premise=draft.synopsis or f"{draft.title} — {draft.genre}",
            world_rules=draft.world.rules if draft.world else [],
        )
        # Tạo các arc dựa trên tổng số chương
        total = len(draft.outlines) or 100
        num_arcs = max(1, (total + arc_size - 1) // arc_size)  # ceiling division
        for i in range(num_arcs):
            start = i * arc_size + 1
            end = min((i + 1) * arc_size, total)
            bible.arcs.append(StoryArc(
                arc_number=i + 1,
                title=f"Arc {i + 1}",
                start_chapter=start,
                end_chapter=end,
            ))
        return bible

    def update_after_chapter(
        self,
        bible: StoryBible,
        chapter: Chapter,
        character_states: list[CharacterState],
        plot_events: list[PlotEvent],
    ) -> None:
        """Cập nhật bible sau khi viết xong một chương."""
        ch_num = chapter.chapter_number

        # Thêm sự kiện mới thành plot threads
        for event in plot_events:
            if event.chapter_number == ch_num:
                thread = PlotThread(
                    thread_id=str(uuid.uuid4())[:8],
                    description=event.event,
                    status="active",
                    started_chapter=ch_num,
                    characters_involved=event.characters_involved,
                )
                bible.active_threads.append(thread)

        # Giữ tối đa 20 thread đang mở (cũ nhất tự động resolved)
        if len(bible.active_threads) > 20:
            overflow = bible.active_threads[:-20]
            for t in overflow:
                t.status = "resolved"
                t.resolved_chapter = ch_num
                bible.resolved_threads.append(t)
            bible.active_threads = bible.active_threads[-20:]

        # Cập nhật milestone events (giữ 30 sự kiện quan trọng nhất)
        for event in plot_events:
            bible.milestone_events.append(
                f"Ch{event.chapter_number}: {event.event}"
            )
        bible.milestone_events = bible.milestone_events[-30:]

        # Đánh dấu arc hoàn tất khi đến cuối arc
        for arc in bible.arcs:
            if arc.status == "active" and ch_num >= arc.end_chapter:
                arc.status = "completed"
                arc.summary = (
                    chapter.summary
                    or f"Arc {arc.arc_number} hoàn tất tại chương {ch_num}"
                )
                bible.arc_summaries.append(f"Arc {arc.arc_number}: {arc.summary}")
                logger.info(f"Arc {arc.arc_number} completed at chapter {ch_num}")

        # Bound resolved_threads and arc_summaries to prevent unbounded growth
        if len(bible.resolved_threads) > 50:
            bible.resolved_threads = bible.resolved_threads[-50:]
        if len(bible.arc_summaries) > 20:
            bible.arc_summaries = bible.arc_summaries[-20:]

    def get_context_for_chapter(
        self,
        bible: StoryBible,
        chapter_num: int,
        recent_summaries: list[str] = None,
        character_states: list[CharacterState] = None,
    ) -> str:
        """Tạo chuỗi context phong phú từ bible cho chương tiếp theo."""
        parts = []

        # 1. Tiền đề truyện (luôn có)
        if bible.premise:
            parts.append(f"## Tiền đề truyện:\n{bible.premise}")

        # 2. Quy tắc thế giới (nén gọn)
        if bible.world_rules:
            rules = "; ".join(bible.world_rules[:5])
            parts.append(f"## Quy tắc thế giới:\n{rules}")

        # 3. Thông tin arc hiện tại
        current_arc = None
        for arc in bible.arcs:
            if arc.start_chapter <= chapter_num <= arc.end_chapter:
                current_arc = arc
                break
        if current_arc:
            parts.append(
                f"## Arc hiện tại: {current_arc.title} "
                f"(ch{current_arc.start_chapter}-{current_arc.end_chapter})"
            )

        # 4. Tóm tắt các arc trước (nén)
        if bible.arc_summaries:
            parts.append(
                "## Tóm tắt các arc trước:\n" + "\n".join(bible.arc_summaries[-3:])
            )

        # 5. Các tuyến truyện đang mở
        if bible.active_threads:
            threads = [
                f"- {t.description} (từ ch{t.started_chapter})"
                for t in bible.active_threads[-10:]
            ]
            parts.append("## Tuyến truyện đang mở:\n" + "\n".join(threads))

        # 6. Sự kiện quan trọng
        if bible.milestone_events:
            parts.append(
                "## Sự kiện quan trọng:\n" + "\n".join(bible.milestone_events[-10:])
            )

        # 7. Tóm tắt các chương gần đây (rolling window)
        if recent_summaries:
            parts.append(
                "## Các chương gần đây:\n" + "\n---\n".join(recent_summaries[-5:])
            )

        # 8. Trạng thái nhân vật
        if character_states:
            char_lines = [
                f"- {cs.name}: {cs.mood}, {cs.arc_position}, last: {cs.last_action}"
                for cs in character_states[:8]
            ]
            parts.append("## Trạng thái nhân vật:\n" + "\n".join(char_lines))

            # 9. Diễn biến mối quan hệ tích lũy
            rel_lines = []
            for cs in character_states[:8]:
                cum_rels = getattr(cs, "cumulative_relationships", [])
                if cum_rels:
                    rel_lines.append(f"- {cs.name}: {'; '.join(cum_rels[-5:])}")
            if rel_lines:
                parts.append("## Diễn biến mối quan hệ:\n" + "\n".join(rel_lines))

        return "\n\n".join(parts)
