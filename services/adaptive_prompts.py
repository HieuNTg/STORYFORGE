"""Adaptive prompt engineering — dynamic prompt modifications based on genre and quality scores."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Genre-specific writing emphasis injected into WRITE_CHAPTER prompt
GENRE_EMPHASIS = {
    "Tiên Hiệp": "Nhấn mạnh hệ thống tu luyện, cảnh giới đột phá, chiến đấu bằng pháp thuật. Dùng ngôn ngữ cổ điển trang trọng.",
    "Huyền Huyễn": "Tập trung vào thế giới quan phong phú, hệ thống năng lực độc đáo, khám phá bí ẩn. Tạo cảm giác kỳ ảo, huyền bí.",
    "Kiếm Hiệp": "Nhấn mạnh võ công, giang hồ, nghĩa khí. Miêu tả chiêu thức sinh động, cảnh chiến đấu mãn nhãn.",
    "Đô Thị": "Phong cách hiện đại, đời thường. Đối thoại tự nhiên, xung đột xã hội, phát triển sự nghiệp.",
    "Ngôn Tình": "Tập trung phát triển tình cảm, đối thoại lãng mạn, miêu tả tâm lý nhân vật sâu sắc. Tạo moment đáng nhớ.",
    "Xuyên Không": "Khai thác sự đối lập giữa hiện đại và quá khứ. Nhân vật dùng kiến thức hiện đại giải quyết vấn đề.",
    "Trọng Sinh": "Nhấn mạnh kinh nghiệm từ kiếp trước, tránh sai lầm cũ, thay đổi vận mệnh. Tạo kịch tính từ biết trước tương lai.",
    "Hệ Thống": "Mô tả rõ ràng hệ thống quest/reward, level up, inventory. Tạo cảm giác game hóa hấp dẫn.",
    "Khoa Huyễn": "Dùng thuật ngữ khoa học, công nghệ tương lai. Tạo cảm giác hard sci-fi nhưng vẫn dễ hiểu.",
    "Trinh Thám": "Xây dựng manh mối, tạo nghi ngờ. Nhịp điệu nhanh, kết chương cliff-hanger. Logic chặt chẽ.",
    "Lịch Sử": "Bám sát bối cảnh lịch sử, ngôn ngữ phù hợp thời đại. Kết hợp sự kiện thật với hư cấu.",
    "Cung Đấu": "Mưu mô, âm mưu chính trị. Đối thoại nhiều tầng nghĩa, thể hiện trí tuệ và mưu lược nhân vật.",
}

PACING_MODIFIERS = {
    "setup": "Chương xây dựng nền tảng: tập trung giới thiệu, miêu tả chi tiết thế giới/nhân vật. Nhịp chậm, tạo atmosphere. Ít action, nhiều nội tâm và đối thoại.",
    "rising": "Chương tăng tension: stakes phải rõ ràng và leo thang. Nhịp nhanh hơn, cắt ngắn miêu tả, tăng đối thoại gay cấn và hành động.",
    "climax": "Chương cao trào: confrontation trực tiếp, stakes cực đại. Câu ngắn, nhịp nhanh, cảm xúc mãnh liệt. Mọi thread active trong arc phải được đẩy lên đỉnh.",
    "cooldown": "Chương nghỉ ngơi: aftermath, reflection, character bonding. Nhịp chậm, introspective. Giải quyết hậu quả, heal wounds, chuẩn bị cho arc tiếp.",
    "twist": "Chương twist: đảo ngược expectation. Build theo 1 hướng rồi lật. Reveal thông tin mới thay đổi mọi thứ. Kết chương phải shocking.",
}

DIALOGUE_STRATEGY = {
    "Tiên Hiệp": "Đối thoại trang trọng, dùng kính ngữ giữa bậc cao. Ngắn gọn, hàm ý sâu. Thi thoảng dùng thơ/câu nói triết lý.",
    "Ngôn Tình": "Đối thoại nhiều tầng cảm xúc, subtext romantic tension. Dùng im lặng và ánh mắt. Banter và teasing tự nhiên.",
    "Trinh Thám": "Đối thoại sắc bén, mỗi câu có thể là manh mối hoặc red herring. Nhân vật che giấu thông tin qua cách nói.",
    "Cung Đấu": "Mỗi câu nói nhiều tầng nghĩa. Lời nói nhẹ nhàng che đậy dao kiếm. Power dynamics rõ trong mỗi cuộc hội thoại.",
    "Đô Thị": "Đối thoại tự nhiên, có slang hiện đại. Phản ánh tầng lớp xã hội qua cách nói. Humor và sarcasm.",
    "Kiếm Hiệp": "Đối thoại ngắn gọn, khí phách. Dùng giang hồ ngữ. Đôi khi nói bằng hành động thay lời.",
    "Huyền Huyễn": "Mix giữa formal và casual tùy context. Thuật ngữ thế giới quan xen lẫn đối thoại thường.",
    "Khoa Huyễn": "Đối thoại technical nhưng accessible. Nhân vật dùng thuật ngữ khoa học tự nhiên.",
    "Xuyên Không": "Contrast giữa ngôn ngữ hiện đại của MC và ngôn ngữ thời đại. Tạo humor từ culture clash.",
    "Trọng Sinh": "MC nói chín chắn bất thường so với tuổi. Đôi khi slip up, lộ knowledge from future.",
    "Lịch Sử": "Ngôn ngữ phù hợp thời đại. Formal trong triều đình, bình dân ngoài chợ. Tránh anachrionism.",
    "Hệ Thống": "Mix game terminology tự nhiên vào đối thoại. System notifications xen kẽ narrative.",
}

# Score-based prompt boosters — injected when specific quality dimensions are weak
SCORE_BOOSTERS = {
    "coherence": "CHÚ Ý ĐẶC BIỆT: Chương trước có vấn đề về mạch lạc. Đảm bảo logic chặt chẽ, không có lỗ hổng cốt truyện, mỗi sự kiện phải có nguyên nhân rõ ràng.",
    "character_consistency": "CHÚ Ý ĐẶC BIỆT: Nhân vật cần nhất quán hơn. Đảm bảo mỗi nhân vật hành xử đúng tính cách đã thiết lập, không đột ngột thay đổi mà không có lý do.",
    "drama": "CHÚ Ý ĐẶC BIỆT: Cần tăng kịch tính. Thêm xung đột, bất ngờ, căng thẳng. Mỗi cảnh phải có stakes rõ ràng, tạo cảm giác urgency.",
    "writing_quality": "CHÚ Ý ĐẶC BIỆT: Cần cải thiện văn phong. Dùng nhiều biện pháp tu từ hơn, câu văn giàu hình ảnh, tránh lặp từ, đa dạng cấu trúc câu.",
}

# Weak score threshold — below this, booster is injected
WEAK_SCORE_THRESHOLD = 3.0


def get_genre_emphasis(genre: str) -> str:
    """Return genre-specific writing emphasis, or empty string if no match."""
    if not genre:
        return ""
    # Try exact match first, then partial match
    if genre in GENRE_EMPHASIS:
        return GENRE_EMPHASIS[genre]
    genre_lower = genre.lower()
    for key, emphasis in GENRE_EMPHASIS.items():
        key_lower = key.lower()
        if key_lower in genre_lower or genre_lower in key_lower:
            return emphasis
    return ""


def get_score_boosters(prev_chapter_scores: Optional[dict] = None) -> str:
    """Generate score-based prompt boosters from previous chapter's scores.

    Args:
        prev_chapter_scores: dict with keys coherence, character_consistency, drama, writing_quality (1-5 scale)

    Returns:
        String of combined boosters for weak dimensions, or empty string.
    """
    if not prev_chapter_scores:
        return ""

    boosters = []
    for dimension, booster_text in SCORE_BOOSTERS.items():
        score = prev_chapter_scores.get(dimension, 5.0)
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        if score < WEAK_SCORE_THRESHOLD:
            boosters.append(booster_text)

    return "\n".join(boosters)


def build_adaptive_write_prompt(
    base_prompt: str,
    genre: str,
    prev_chapter_scores: Optional[dict] = None,
    pacing_type: str = "",
) -> str:
    """Enhance WRITE_CHAPTER prompt with genre emphasis, score boosters, pacing, and dialogue strategy.

    Args:
        base_prompt: The formatted WRITE_CHAPTER prompt string
        genre: Story genre string
        prev_chapter_scores: Optional dict of previous chapter's dimension scores
        pacing_type: Optional pacing type (setup/rising/climax/cooldown/twist)

    Returns:
        Enhanced prompt with genre emphasis, pacing modifier, dialogue strategy, and score boosters.
    """
    additions = []

    genre_text = get_genre_emphasis(genre)
    if genre_text:
        additions.append(f"HƯỚNG DẪN THỂ LOẠI {genre.upper()}:\n{genre_text}")

    if pacing_type and pacing_type in PACING_MODIFIERS:
        additions.append(f"HƯỚNG DẪN NHỊP ĐỘ ({pacing_type.upper()}):\n{PACING_MODIFIERS[pacing_type]}")

    if genre in DIALOGUE_STRATEGY:
        additions.append(f"CHIẾN LƯỢC ĐỐI THOẠI ({genre}):\n{DIALOGUE_STRATEGY[genre]}")

    booster_text = get_score_boosters(prev_chapter_scores)
    if booster_text:
        additions.append(booster_text)

    if not additions:
        return base_prompt

    # Insert before "YÊU CẦU:" section in the prompt
    insert_text = "\n\n".join(additions) + "\n\n"
    if "YÊU CẦU:" in base_prompt:
        return base_prompt.replace("YÊU CẦU:", insert_text + "YÊU CẦU:")
    # Fallback: prepend before "Bắt đầu viết chương:"
    if "Bắt đầu viết chương:" in base_prompt:
        return base_prompt.replace("Bắt đầu viết chương:", insert_text + "Bắt đầu viết chương:")
    # Last resort: append
    return base_prompt + "\n\n" + insert_text


def build_adaptive_enhance_prompt(
    base_prompt: str,
    genre: str,
) -> str:
    """Enhance ENHANCE_CHAPTER prompt with genre-specific writing guidance.

    Args:
        base_prompt: The formatted ENHANCE_CHAPTER prompt string
        genre: Story genre string

    Returns:
        Enhanced prompt with genre emphasis.
    """
    genre_text = get_genre_emphasis(genre)
    if not genre_text:
        return base_prompt

    insert = f"PHONG CÁCH THỂ LOẠI {genre.upper()}:\n{genre_text}\n\n"
    if "YÊU CẦU:" in base_prompt:
        return base_prompt.replace("YÊU CẦU:", insert + "YÊU CẦU:")
    return base_prompt + "\n\n" + insert
