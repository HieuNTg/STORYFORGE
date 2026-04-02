"""Vietnamese genre-specific drama patterns and escalation rules."""

GENRE_DRAMA_RULES: dict[str, dict] = {
    "Tiên Hiệp": {
        "escalation_pattern": "power_progression",
        "key_beats": [
            "Nhân vật chính đột phá → đối thủ đạt sức mạnh cao hơn",
            "Bí kíp ẩn giấu được tiết lộ tại thời điểm quyết định",
            "Hạt giống phản bội sư phụ ở ~40% truyện",
            "Leo thang giải đấu tông môn",
        ],
        "tension_curve": "ascending_steps",
        "dialogue_style": "trang trọng võ hiệp",
        "emotional_peaks": ["đột phá", "cận tử", "tiết lộ sức mạnh"],
        "pacing_note": "Khoảng cách sức mạnh < 1.5 lần phản diện → kích hoạt chương đột phá",
    },
    "Huyền Huyễn": {
        "escalation_pattern": "mystery_reveal",
        "key_beats": [
            "Phát hiện quy luật thế giới thay đổi tất cả",
            "Kích hoạt huyết mạch/thần khí ẩn giấu",
            "Phản bội liên minh trong lúc khủng hoảng",
            "Thăng cảnh giới là cột mốc truyện",
        ],
        "tension_curve": "ascending_steps",
        "dialogue_style": "thần bí trang trọng",
        "emotional_peaks": ["phá cảnh", "tiết lộ bí mật", "hy sinh"],
        "pacing_note": "Lớp bí ẩn mới mỗi 10-15 chương",
    },
    "Đô Thị": {
        "escalation_pattern": "social_climbing",
        "key_beats": [
            "Leo thang cạnh tranh thương trường",
            "Lộ danh tính bí mật",
            "Xung đột gia tộc sâu sắc hơn",
            "Cấu trúc quyền lực sụp đổ",
        ],
        "tension_curve": "wave",
        "dialogue_style": "hiện đại sắc bén",
        "emotional_peaks": ["bẽ mặt công khai", "trả thù thành công", "bí mật bại lộ"],
        "pacing_note": "Thay đổi địa vị xã hội mỗi 5-8 chương",
    },
    "Ngôn Tình": {
        "escalation_pattern": "emotional_cycle",
        "key_beats": [
            "Hiểu lầm → chiến tranh lạnh → hòa giải",
            "Kích hoạt ghen tuông từ bên thứ ba",
            "Hy sinh tiết lộ tình cảm thật",
            "Mối đe dọa bên ngoài buộc hợp tác",
        ],
        "tension_curve": "oscillating",
        "dialogue_style": "thân mật cảm xúc",
        "emotional_peaks": ["đau lòng", "tỏ tình", "đoàn tụ"],
        "pacing_note": "Chu kỳ cảm xúc mỗi 5-7 chương. Mật độ đối thoại cao.",
    },
    "Cung Đấu": {
        "escalation_pattern": "faction_warfare",
        "key_beats": [
            "Liên minh đa phe thay đổi",
            "Âm mưu đầu độc/ám sát",
            "Thao túng ân sủng chính trị",
            "Thế lực mới xuất hiện buộc tái cân bằng",
        ],
        "tension_curve": "escalating_spiral",
        "dialogue_style": "cung đình mưu mô",
        "emotional_peaks": ["lộ phản bội", "đoạt quyền", "đồng minh ngã"],
        "pacing_note": "Thế lực mới mỗi N chương. Cảm xúc dao động 30-40%.",
    },
    "Xuyên Không": {
        "escalation_pattern": "knowledge_advantage",
        "key_beats": [
            "Kiến thức tương lai tạo lợi thế",
            "Hiệu ứng cánh bướm gây khủng hoảng bất ngờ",
            "Sự kiện lịch sử chệch hướng",
            "Bí mật danh tính đe dọa bại lộ",
        ],
        "tension_curve": "wave",
        "dialogue_style": "pha trộn thời đại",
        "emotional_peaks": ["khủng hoảng thời gian", "lộ danh tính", "thay đổi lịch sử"],
        "pacing_note": "Lợi thế kiến thức giảm dần → cần xung đột mới",
    },
    "Trọng Sinh": {
        "escalation_pattern": "revenge_arc",
        "key_beats": [
            "Giai đoạn thực hiện kế hoạch trả thù",
            "Kẻ thù phát hiện lợi thế nhân vật chính",
            "Đồng minh cũ trở thành mối đe dọa",
            "Hiệu ứng cánh bướm từ quyết định thay đổi",
        ],
        "tension_curve": "ascending_steps",
        "dialogue_style": "tính toán lạnh lùng",
        "emotional_peaks": ["trả thù xong", "mối đe dọa mới", "lưỡng nan đạo đức"],
        "pacing_note": "Mỗi mục tiêu trả thù = một arc. Mối đe dọa mới từ thời gian thay đổi.",
    },
    "Kiếm Hiệp": {
        "escalation_pattern": "honor_conflict",
        "key_beats": [
            "Leo thang giải đấu võ thuật",
            "Tình nghĩa sư đồ bị thử thách",
            "Lưỡng nan giữa công lý và trung thành",
            "Phát hiện tuyệt kỹ cuối cùng",
        ],
        "tension_curve": "ascending_steps",
        "dialogue_style": "cổ điển hào hiệp",
        "emotional_peaks": ["cao trào quyết đấu", "bị đồng minh phản bội", "hy sinh vì danh dự"],
        "pacing_note": "Lưỡng nan danh dự mỗi 8-10 chương",
    },
}


def get_genre_rules(genre: str) -> dict:
    """Get drama rules for genre. Falls back to generic if not found."""
    # Try exact match first
    if genre in GENRE_DRAMA_RULES:
        return GENRE_DRAMA_RULES[genre]
    # Try partial match (Vietnamese genre names can vary)
    genre_lower = genre.lower()
    for key, rules in GENRE_DRAMA_RULES.items():
        if key.lower() in genre_lower or genre_lower in key.lower():
            return rules
    # Generic fallback
    return {
        "escalation_pattern": "standard",
        "key_beats": ["Leo thang xung đột", "Tiết lộ nhân vật", "Đối đầu cao trào"],
        "tension_curve": "ascending",
        "dialogue_style": "tự nhiên",
        "emotional_peaks": ["cao trào", "tiết lộ", "giải quyết"],
        "pacing_note": "Cung kịch tiêu chuẩn",
    }


def get_genre_enhancement_hints(genre: str, chapter_num: int, total_chapters: int) -> str:
    """Generate genre-specific enhancement hints for a chapter position."""
    rules = get_genre_rules(genre)
    position = chapter_num / max(total_chapters, 1)

    hints = [f"Thể loại: {genre} — Phong cách đối thoại: {rules['dialogue_style']}"]

    # Position-based beat suggestion
    if position < 0.25:
        hints.append(f"Giai đoạn mở đầu — thiết lập: {rules['key_beats'][0]}")
    elif position < 0.5:
        hints.append(f"Giai đoạn phát triển — leo thang: {rules['key_beats'][1]}")
        if rules['escalation_pattern'] == 'power_progression' and position > 0.35:
            hints.append("⚡ Đây là thời điểm seed phản bội sư phụ (~40% truyện)")
    elif position < 0.75:
        hints.append(f"Giai đoạn cao trào — xung đột: {rules['key_beats'][2]}")
    else:
        hints.append(f"Giai đoạn kết — giải quyết: {rules['key_beats'][3]}")

    # Emotional peak suggestions
    peak_text = ", ".join(rules['emotional_peaks'])
    hints.append(f"Đỉnh cảm xúc cần hướng tới: {peak_text}")
    hints.append(f"Lưu ý pacing: {rules['pacing_note']}")

    return "\n".join(hints)
