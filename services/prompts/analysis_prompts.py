"""Layer 2 prompts — drama simulation, escalation, feedback, analytics, revision.

Covers agent personas, drama evaluation, chapter enhancement, emotion
extraction, and smart chapter revision.
"""

ANALYZE_STORY = """Bạn là nhà phân tích truyện chuyên sâu.
Hãy phân tích câu truyện sau và trích xuất thông tin:

TIÊU ĐỀ: {title}
THỂ LOẠI: {genre}
NHÂN VẬT: {characters}
NỘI DUNG TÓM TẮT: {synopsis}

Trả về JSON:
{{
  "relationships": [
    {{
      "character_a": "tên A",
      "character_b": "tên B",
      "relation_type": "đồng_minh/đối_thủ/tình_nhân/sư_phụ/kẻ_thù/gia_đình/phản_bội/chưa_rõ",
      "intensity": 0.7,
      "description": "mô tả mối quan hệ",
      "tension": 0.5
    }}
  ],
  "conflict_points": ["điểm xung đột hiện tại"],
  "untapped_drama": ["tiềm năng kịch tính chưa khai thác"],
  "character_weaknesses": {{"tên": "điểm yếu/bí mật"}}
}}"""

AGENT_PERSONA = """Bạn là {character_name}, một nhân vật trong truyện {genre}.

THÔNG TIN CỦA BẠN:
- Tính cách: {personality}
- Tiểu sử: {background}
- Động lực: {motivation}
- Mối quan hệ: {relationships}

BỐI CẢNH HIỆN TẠI:
{current_context}

CÁC BÀI VIẾT/HÀNH ĐỘNG GẦN ĐÂY CỦA NHÂN VẬT KHÁC:
{recent_posts}

Hãy phản ứng tự nhiên theo tính cách của bạn. Bạn có thể:
1. Đăng suy nghĩ/cảm xúc của mình
2. Phản hồi hành động của nhân vật khác
3. Tiết lộ bí mật hoặc tạo xung đột
4. Kết minh hoặc phản bội

Trả về JSON:
{{
  "action_type": "post/comment/reaction/confrontation",
  "content": "nội dung hành động/lời nói",
  "target": "nhân vật mục tiêu (nếu có)",
  "sentiment": "tích cực/tiêu cực/trung lập/căng thẳng",
  "hidden_motive": "động cơ ẩn sau hành động"
}}"""

EVALUATE_DRAMA = """Bạn là đạo diễn kịch tính, đánh giá các sự kiện mô phỏng.

CÁC HÀNH ĐỘNG TRONG VÒNG MÔ PHỎNG NÀY:
{actions}

MỐI QUAN HỆ HIỆN TẠI:
{relationships}

Hãy đánh giá và tạo sự kiện kịch tính:

Trả về JSON:
{{
  "events": [
    {{
      "event_type": "xung_đột/liên_minh/phản_bội/tiết_lộ/đối_đầu",
      "characters_involved": ["tên"],
      "description": "mô tả sự kiện",
      "drama_score": 0.8,
      "suggested_insertion": "gợi ý chèn vào chương nào/vị trí nào"
    }}
  ],
  "relationship_changes": [
    {{
      "character_a": "tên",
      "character_b": "tên",
      "old_relation": "loại cũ",
      "new_relation": "loại mới",
      "reason": "lý do thay đổi"
    }}
  ],
  "overall_drama_score": 0.7
}}"""

ENHANCE_CHAPTER = """Bạn là nhà văn tài năng chuyên viết truyện {genre_style}. Hãy viết lại chương truyện sau.

CHƯƠNG GỐC:
{original_chapter}

CÁC SỰ KIỆN KỊCH TÍNH CẦN THÊM:
{drama_events}

GỢI Ý TĂNG CƯỜNG:
{suggestions}

MỐI QUAN HỆ ĐÃ CẬP NHẬT:
{updated_relationships}

HƯỚNG DẪN THỂ LOẠI:
{genre_hints}

ĐIỂM MẠNH CẦN GIỮ:
{strong_points}

YÊU CẦU:
- Giữ cốt truyện chính, tăng kịch tính tại các điểm yếu đã chỉ ra
- Tăng xung đột nội tâm nhân vật
- Thêm twist tự nhiên, không gượng ép
- Đối thoại sắc bén theo phong cách thể loại
- Cliffhanger mạnh mẽ cuối chương
- Cảm xúc sâu sắc, phù hợp emotional arc
- Khoảng {word_count} từ, viết hoàn toàn tiếng Việt

Bắt đầu viết lại:"""

DRAMA_SUGGESTIONS = """Dựa trên kết quả mô phỏng tương tác nhân vật, hãy đề xuất cách làm truyện kịch tích hơn.

KẾT QUẢ MÔ PHỎNG:
{simulation_summary}

TRUYỆN GỐC (tóm tắt):
{story_summary}

Trả về JSON:
{{
  "suggestions": [
    "gợi ý tăng kịch tính 1",
    "gợi ý tăng kịch tính 2"
  ],
  "character_arcs": {{
    "tên nhân vật": "hướng phát triển mới đề xuất"
  }},
  "tension_points": {{
    "chương X": 0.8
  }}
}}"""

