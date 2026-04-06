"""Theo dõi sự thay đổi giữa chương gốc và chương đã tăng cường.

Cung cấp thông tin minh bạch về những gì Layer 2 đã sửa đổi:
cảnh thêm/bớt, thay đổi đối thoại, điều chỉnh nhịp độ.
Không gây lỗi nghiêm trọng — dùng để debug và phân tích chất lượng.
"""

import logging
import difflib

logger = logging.getLogger(__name__)


def compute_chapter_diff(original_content: str, enhanced_content: str) -> list[str]:
    """Tính changelog dạng người đọc được giữa chương gốc và chương đã tăng cường.

    Trả về danh sách mô tả các thay đổi.
    """
    if not original_content or not enhanced_content:
        return ["Không có dữ liệu so sánh"]

    orig_lines = original_content.splitlines()
    enhanced_lines = enhanced_content.splitlines()

    changelog = []

    # Thay đổi số từ
    orig_words = len(original_content.split())
    enhanced_words = len(enhanced_content.split())
    delta = enhanced_words - orig_words
    if abs(delta) > 50:
        direction = "tăng" if delta > 0 else "giảm"
        changelog.append(f"Số từ {direction} {abs(delta)} ({orig_words} → {enhanced_words})")

    # Thay đổi mật độ đối thoại
    orig_dialogue = sum(1 for l in orig_lines if l.strip().startswith(("\"", "\u201c", "—", "–")))
    enhanced_dialogue = sum(1 for l in enhanced_lines if l.strip().startswith(("\"", "\u201c", "—", "–")))
    if abs(enhanced_dialogue - orig_dialogue) > 2:
        direction = "tăng" if enhanced_dialogue > orig_dialogue else "giảm"
        changelog.append(f"Đối thoại {direction} ({orig_dialogue} → {enhanced_dialogue} dòng)")

    # Thay đổi cấu trúc đoạn
    orig_paras = len([l for l in orig_lines if l.strip() == ""])
    enhanced_paras = len([l for l in enhanced_lines if l.strip() == ""])
    if abs(enhanced_paras - orig_paras) > 3:
        changelog.append(f"Cấu trúc đoạn thay đổi ({orig_paras} → {enhanced_paras} đoạn)")

    # Tỉ lệ tương đồng
    ratio = difflib.SequenceMatcher(None, original_content[:3000], enhanced_content[:3000]).ratio()
    if ratio < 0.3:
        changelog.append(f"Viết lại gần như hoàn toàn (similarity: {ratio:.0%})")
    elif ratio < 0.6:
        changelog.append(f"Thay đổi đáng kể (similarity: {ratio:.0%})")
    elif ratio < 0.85:
        changelog.append(f"Sửa đổi vừa phải (similarity: {ratio:.0%})")
    else:
        changelog.append(f"Thay đổi nhỏ (similarity: {ratio:.0%})")

    return changelog or ["Không phát hiện thay đổi đáng kể"]


def track_enhancement_diffs(
    original_chapters: list,
    enhanced_chapters: list,
) -> dict[int, list[str]]:
    """Theo dõi diff cho tất cả chương. Trả về {chapter_number: [changes]}.

    Cũng gán enhancement_changelog vào từng chương đã tăng cường nếu trường tồn tại.
    """
    diffs: dict[int, list[str]] = {}

    originals_by_num = {ch.chapter_number: ch for ch in original_chapters}

    for enhanced_ch in enhanced_chapters:
        original_ch = originals_by_num.get(enhanced_ch.chapter_number)
        if not original_ch:
            diffs[enhanced_ch.chapter_number] = ["Chương mới (không có bản gốc)"]
            continue

        changelog = compute_chapter_diff(original_ch.content, enhanced_ch.content)
        diffs[enhanced_ch.chapter_number] = changelog

        # Gán vào chương nếu trường tồn tại
        if hasattr(enhanced_ch, "enhancement_changelog"):
            enhanced_ch.enhancement_changelog = changelog

    total_changes = sum(len(v) for v in diffs.values())
    logger.info(
        f"Theo dõi diff tăng cường: {total_changes} thay đổi trên {len(diffs)} chương"
    )

    return diffs
