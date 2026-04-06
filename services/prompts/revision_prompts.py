"""Escalation, feedback, analytics, and smart revision prompts.

Covers escalation events, drama checks, re-enhancement, emotion
extraction, RAG context, and smart chapter revision.
"""

ESCALATION_EVENT = """Dựa trên mối quan hệ căng thẳng giữa các nhân vật, hãy tạo một sự kiện kịch tính.

LOẠI KỊCH BẢN: {pattern_type}
NHÂN VẬT LIÊN QUAN: {characters}
MỐI QUAN HỆ: {relationship}
THỂ LOẠI: {genre}

Trả về JSON:
{{"event_type": "{pattern_type}", "description": "mô tả sự kiện kịch tính", "characters_involved": [{characters_list}], "drama_score": 0.8, "suggested_insertion": ""}}"""

QUICK_DRAMA_CHECK = """Đánh giá chi tiết mức kịch tính của chương truyện sau.

NỘI DUNG:
{content}

Phân tích theo 5 tiêu chí (0-1 mỗi tiêu chí):
1. conflict_tension: Mức xung đột/căng thẳng
2. dialogue_quality: Đối thoại sắc bén, có chiều sâu
3. emotional_depth: Chiều sâu cảm xúc nhân vật
4. pacing: Nhịp độ phù hợp (không quá nhanh/chậm)
5. cliffhanger: Kết chương hấp dẫn

Trả về JSON:
{{"drama_score": 0.7, "conflict_tension": 0.6, "dialogue_quality": 0.7, "emotional_depth": 0.5, "pacing": 0.8, "cliffhanger": 0.6, "weak_points": ["điểm yếu cụ thể 1", "điểm yếu 2"], "strong_points": ["điểm mạnh cần giữ"]}}"""

REENHANCE_CHAPTER = """Viết lại chương truyện sau, tập trung CỤ THỂ vào các điểm yếu đã phân tích.

CHƯƠNG GỐC:
{chapter_content}

PHÂN TÍCH ĐIỂM YẾU (cần sửa):
{weak_points}

ĐIỂM MẠNH (PHẢI GIỮ NGUYÊN):
{strong_points}

HƯỚNG DẪN THỂ LOẠI:
{genre_hints}

YÊU CẦU:
- CHỈ cải thiện các điểm yếu đã liệt kê, KHÔNG thay đổi điểm mạnh
- Giữ cốt truyện, tăng kịch tính tại các điểm yếu
- Khoảng {word_count} từ
- Viết hoàn toàn bằng tiếng Việt

Bắt đầu viết lại:"""

RAG_CONTEXT_SECTION = """
## Tài liệu tham khảo:
{rag_context}
Sử dụng thông tin trên để làm phong phú bối cảnh, nhưng không sao chép nguyên văn.
"""

EXTRACT_CHAPTER_EMOTIONS = """Phân tích cảm xúc trong đoạn văn sau và trả về JSON:

Chương {chapter_number}: {title}
---
{content}
---

Ví dụ output:
{{
  "joy": 3,
  "sadness": 7,
  "anger": 2,
  "fear": 5,
  "surprise": 8,
  "tension": 6,
  "romance": 1,
  "dominant_emotion": "buồn",
  "emotional_summary": "Chương mang âm hưởng buồn với nhiều mất mát và nuối tiếc"
}}

Trả về JSON với format:
{{
  "joy": <0-10>,
  "sadness": <0-10>,
  "anger": <0-10>,
  "fear": <0-10>,
  "surprise": <0-10>,
  "tension": <0-10>,
  "romance": <0-10>,
  "dominant_emotion": "<tên cảm xúc chiếm chủ đạo>",
  "emotional_summary": "<mô tả ngắn 1 câu về cung bậc cảm xúc>"
}}

Chú ý: Đánh giá dựa trên NỘI DUNG và NGỮ CẢNH, không chỉ từ khóa.
Chỉ trả về JSON, không giải thích."""

SMART_REVISE_CHAPTER = """Bạn là nhà văn chuyên nghiệp. Hãy sửa lại chương truyện dựa trên phản hồi cụ thể từ ban biên tập.

CHƯƠNG {chapter_number}: {title}

NỘI DUNG GỐC:
{content}

CÁC VẤN ĐỀ CẦN SỬA (từ phản hồi biên tập):
{issues}

GỢI Ý CẢI THIỆN:
{suggestions}

THỂ LOẠI: {genre}

YÊU CẦU BẮT BUỘC:
- CHỈ sửa các vấn đề đã liệt kê ở trên
- Áp dụng các gợi ý cải thiện
- KHÔNG thay đổi cốt truyện, nhân vật, dòng thời gian
- KHÔNG thêm nhân vật mới hoặc tình tiết mới
- Giữ nguyên phong cách và giọng văn
- Khoảng {word_count} từ (+/- 10%)
- Viết hoàn toàn bằng tiếng Việt

Bắt đầu viết lại chương:"""

COHERENCE_FIX = """Sửa chương truyện sau để giải quyết các vấn đề nhất quán.

CHƯƠNG {chapter_number}: {title}

NỘI DUNG:
{content}

VẤN ĐỀ CẦN SỬA:
{issues}

GỢI Ý SỬA:
{fix_suggestion}

YÊU CẦU:
- CHỈ sửa các vấn đề nhất quán đã liệt kê
- KHÔNG thay đổi cốt truyện chính hoặc giảm kịch tính
- Giữ nguyên phong cách và giọng văn
- Khoảng {word_count} từ
- Viết hoàn toàn bằng tiếng Việt

Bắt đầu viết lại:"""
