"""Tất cả prompt templates cho pipeline - Tiếng Việt."""

# ============================================================
# LAYER 1: TẠO TRUYỆN
# ============================================================

SUGGEST_TITLE = """Bạn là nhà văn sáng tạo chuyên viết truyện {genre}.
Hãy đề xuất 5 tiêu đề hấp dẫn cho một câu truyện thuộc thể loại {genre}.
Yêu cầu thêm: {requirements}

Trả về JSON: {{"titles": ["tiêu đề 1", "tiêu đề 2", ...]}}"""

GENERATE_CHARACTERS = """Bạn là nhà văn chuyên xây dựng nhân vật cho truyện {genre}.
Tiêu đề truyện: {title}
Ý tưởng: {idea}

Hãy tạo {num_characters} nhân vật với thông tin chi tiết.
Đảm bảo có xung đột nội tâm, mối quan hệ phức tạp giữa các nhân vật.

Trả về JSON:
{{
  "characters": [
    {{
      "name": "tên",
      "role": "chính/phụ/phản diện",
      "personality": "tính cách chi tiết",
      "background": "tiểu sử",
      "motivation": "động lực hành động",
      "appearance": "ngoại hình",
      "relationships": ["mô tả mối quan hệ với nhân vật khác"]
    }}
  ]
}}"""

GENERATE_WORLD = """Bạn là kiến trúc sư thế giới cho truyện {genre}.
Tiêu đề: {title}
Nhân vật: {characters}

Hãy xây dựng bối cảnh thế giới chi tiết, phong phú.

Trả về JSON:
{{
  "name": "tên thế giới",
  "description": "mô tả tổng quan",
  "rules": ["quy tắc 1", "quy tắc 2"],
  "locations": ["địa điểm quan trọng"],
  "era": "thời đại"
}}"""

GENERATE_OUTLINE = """Bạn là biên kịch chuyên xây dựng cốt truyện {genre}.
Tiêu đề: {title}
Nhân vật: {characters}
Bối cảnh: {world}
Ý tưởng: {idea}

Hãy tạo dàn ý chi tiết cho {num_chapters} chương.
Mỗi chương cần có: cao trào, xung đột, phát triển nhân vật.
Cốt truyện phải có nhịp điệu: giới thiệu → phát triển → cao trào → kết thúc.

Trả về JSON:
{{
  "synopsis": "tóm tắt toàn bộ truyện",
  "outlines": [
    {{
      "chapter_number": 1,
      "title": "tiêu đề chương",
      "summary": "tóm tắt nội dung",
      "key_events": ["sự kiện 1", "sự kiện 2"],
      "characters_involved": ["tên nhân vật"],
      "emotional_arc": "cung bậc cảm xúc chương này"
    }}
  ]
}}"""

WRITE_CHAPTER = """Bạn là tiểu thuyết gia tài năng chuyên viết {genre} bằng tiếng Việt.

Phong cách viết: {style}
Tiêu đề truyện: {title}
Bối cảnh thế giới: {world}

NHÂN VẬT:
{characters}

DÀN Ý CHƯƠNG {chapter_number} - {chapter_title}:
{outline}

NỘI DUNG CÁC CHƯƠNG TRƯỚC (tóm tắt):
{previous_summary}

YÊU CẦU:
- Viết chương {chapter_number} đầy đủ, khoảng {word_count} từ
- Miêu tả sinh động, đối thoại tự nhiên
- Thể hiện rõ tính cách nhân vật qua hành động và lời nói
- Tạo nhịp điệu kịch tính, có cao trào
- Kết chương tạo sự tò mò cho chương tiếp theo
- Viết hoàn toàn bằng tiếng Việt

Bắt đầu viết chương:"""

SUMMARIZE_CHAPTER = """Tóm tắt ngắn gọn nội dung chương truyện sau trong 3-5 câu,
tập trung vào sự kiện chính và phát triển nhân vật:

{content}"""

EXTRACT_CHARACTER_STATE = """Phân tích chương truyện sau và trích xuất trạng thái hiện tại của từng nhân vật.

NỘI DUNG CHƯƠNG:
{content}

DANH SÁCH NHÂN VẬT CẦN THEO DÕI:
{characters}

Trả về JSON:
{{
  "character_states": [
    {{
      "name": "tên nhân vật",
      "mood": "tâm trạng hiện tại",
      "arc_position": "rising/crisis/falling/resolution",
      "knowledge": ["điều nhân vật biết được trong chương này"],
      "relationship_changes": ["thay đổi mối quan hệ"],
      "last_action": "hành động cuối cùng trong chương"
    }}
  ]
}}"""

EXTRACT_PLOT_EVENTS = """Trích xuất các sự kiện quan trọng từ chương truyện sau.
Chỉ liệt kê sự kiện có ảnh hưởng đến cốt truyện.

NỘI DUNG CHƯƠNG {chapter_number}:
{content}

Trả về JSON:
{{
  "events": [
    {{
      "event": "mô tả ngắn gọn sự kiện",
      "characters_involved": ["tên nhân vật liên quan"]
    }}
  ]
}}"""

# ============================================================
# LAYER 2: MÔ PHỎNG TĂNG KỊCH TÍNH (MiroFish-inspired)
# ============================================================

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

ENHANCE_CHAPTER = """Bạn là nhà văn tài năng. Hãy viết lại chương truyện sau để tăng tính kịch tính.

CHƯƠNG GỐC:
{original_chapter}

CÁC SỰ KIỆN KỊCH TÍNH CẦN THÊM VÀO:
{drama_events}

GỢI Ý TĂNG CƯỜNG:
{suggestions}

MỐI QUAN HỆ ĐÃ CẬP NHẬT:
{updated_relationships}

YÊU CẦU:
- Giữ nguyên cốt truyện chính nhưng thêm các yếu tố kịch tính
- Tăng cường xung đột nội tâm nhân vật
- Thêm twist, bất ngờ tự nhiên
- Đối thoại sắc bén, căng thẳng hơn
- Tạo cliffhanger mạnh mẽ hơn
- Miêu tả cảm xúc sâu sắc hơn
- Khoảng {word_count} từ
- Viết hoàn toàn bằng tiếng Việt

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

# ============================================================
# LAYER 3: VIDEO / STORYBOARD
# ============================================================

GENERATE_STORYBOARD = """Bạn là đạo diễn phim chuyên chuyển thể truyện thành phim ngắn.

CHƯƠNG TRUYỆN:
{chapter_content}

NHÂN VẬT TRONG CHƯƠNG:
{characters}

ĐỊA ĐIỂM:
{locations}

Hãy tạo storyboard gồm {num_shots} shot cho chương này.

Trả về JSON:
{{
  "panels": [
    {{
      "panel_number": 1,
      "shot_type": "toàn_cảnh/trung_cảnh/cận_cảnh/đặc_tả/qua_vai/góc_nhìn_nhân_vật/từ_trên_cao",
      "description": "mô tả hình ảnh chi tiết",
      "camera_movement": "tĩnh/lia ngang/zoom in/zoom out/theo nhân vật/xoay",
      "dialogue": "lời thoại nhân vật (nếu có)",
      "narration": "lời kể (nếu có)",
      "mood": "tâm trạng/không khí",
      "characters_in_frame": ["tên nhân vật"],
      "duration_seconds": 5,
      "image_prompt": "prompt tiếng Anh để tạo hình ảnh AI",
      "sound_effect": "hiệu ứng âm thanh gợi ý"
    }}
  ]
}}"""

GENERATE_VOICE_SCRIPT = """Bạn là đạo diễn lồng tiếng cho phim hoạt hình/drama ngắn.

STORYBOARD:
{storyboard}

THÔNG TIN NHÂN VẬT:
{characters}

Hãy tạo kịch bản lồng tiếng cho từng panel.

Trả về JSON:
{{
  "voice_lines": [
    {{
      "character": "tên nhân vật hoặc 'người_kể_chuyện'",
      "text": "nội dung lời thoại/kể chuyện",
      "emotion": "cảm xúc: bình thường/vui/buồn/giận/sợ/ngạc nhiên/quyết tâm",
      "panel_number": 1
    }}
  ],
  "character_voice_descriptions": {{
    "tên nhân vật": "mô tả giọng nói: giới tính, độ tuổi, tông giọng"
  }}
}}"""

CHARACTER_IMAGE_PROMPT = """Dựa trên mô tả nhân vật sau, tạo prompt tiếng Anh để generate hình ảnh nhân vật.

Nhân vật: {name}
Ngoại hình: {appearance}
Tính cách: {personality}
Thể loại truyện: {genre}

Trả về JSON:
{{
  "image_prompt": "detailed English prompt for AI image generation",
  "negative_prompt": "things to avoid in the image"
}}"""

LOCATION_IMAGE_PROMPT = """Dựa trên mô tả địa điểm sau, tạo prompt tiếng Anh để generate hình ảnh.

Địa điểm: {location}
Thể loại truyện: {genre}
Không khí: {mood}

Trả về JSON:
{{
  "image_prompt": "detailed English prompt for AI image generation",
  "negative_prompt": "things to avoid"
}}"""
