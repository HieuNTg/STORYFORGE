"""Layer 1 prompts — story generation (titles, characters, world, outline, chapters).

All prompts are Vietnamese by default. localize_prompt() handles runtime
translation when config.pipeline.language != "vi".
"""

# vi-only
SUGGEST_TITLE = """Bạn là nhà văn sáng tạo chuyên viết truyện {genre}.
Hãy đề xuất 5 tiêu đề hấp dẫn cho một câu truyện thuộc thể loại {genre}.
Yêu cầu thêm: {requirements}

BẮT BUỘC: Viết tiêu đề bằng tiếng Việt.

Trả về JSON: {{"titles": ["tiêu đề 1", "tiêu đề 2", ...]}}"""

# vi-only
GENERATE_CHARACTERS = """Bạn là nhà văn chuyên xây dựng nhân vật cho truyện {genre}.
Tiêu đề truyện: {title}
Ý tưởng: {idea}

Hãy tạo {num_characters} nhân vật với thông tin chi tiết.
Đảm bảo có xung đột nội tâm, mối quan hệ phức tạp giữa các nhân vật.
BẮT BUỘC: Toàn bộ nội dung (tên, tính cách, tiểu sử...) phải viết bằng tiếng Việt.

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

# vi-only
GENERATE_WORLD = """Bạn là kiến trúc sư thế giới cho truyện {genre}.
Tiêu đề: {title}
Nhân vật: {characters}

Hãy xây dựng bối cảnh thế giới chi tiết, phong phú.
BẮT BUỘC: Viết toàn bộ bằng tiếng Việt.

Trả về JSON:
{{
  "name": "tên thế giới",
  "description": "mô tả tổng quan",
  "rules": ["quy tắc 1", "quy tắc 2"],
  "locations": ["địa điểm quan trọng"],
  "era": "thời đại"
}}"""

# vi-only
GENERATE_OUTLINE = """Bạn là biên kịch chuyên xây dựng cốt truyện {genre}.
Tiêu đề: {title}
Nhân vật: {characters}
Bối cảnh: {world}
Ý tưởng: {idea}

Hãy tạo dàn ý chi tiết cho {num_chapters} chương.
Mỗi chương cần có: cao trào, xung đột, phát triển nhân vật.
Cốt truyện phải có nhịp điệu: giới thiệu → phát triển → cao trào → kết thúc.
BẮT BUỘC: Viết toàn bộ nội dung (tiêu đề chương, tóm tắt, sự kiện...) bằng tiếng Việt.

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

CONTINUE_OUTLINE = """Bạn là biên kịch chuyên xây dựng cốt truyện {genre}.
Tiêu đề: {title}
Nhân vật: {characters}
Bối cảnh: {world}

TRUYỆN HIỆN TẠI ({existing_chapters} chương):
Tóm tắt: {synopsis}

CÁC CHƯƠNG ĐÃ CÓ:
{existing_outlines}

TRẠNG THÁI NHÂN VẬT HIỆN TẠI:
{character_states}

SỰ KIỆN QUAN TRỌNG ĐÃ XẢY RA:
{plot_events}

Hãy tạo dàn ý cho {additional_chapters} chương tiếp theo (bắt đầu từ chương {start_chapter}).
Cốt truyện phải tiếp nối tự nhiên, phát triển xung đột, và tiến tới cao trào.

Trả về JSON:
{{
  "outlines": [
    {{
      "chapter_number": {start_chapter},
      "title": "tiêu đề chương",
      "summary": "tóm tắt nội dung",
      "key_events": ["sự kiện 1", "sự kiện 2"],
      "characters_involved": ["tên nhân vật"],
      "emotional_arc": "cung bậc cảm xúc chương này"
    }}
  ]
}}"""

# vi-only
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

# vi-only
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

SCORE_CHAPTER = """Đánh giá chương truyện sau theo 4 tiêu chí (thang điểm 1-5, trong đó 1=rất kém, 3=trung bình, 5=xuất sắc):

1. **coherence:** Cốt truyện logic, mạch lạc, không mâu thuẫn
2. **character_consistency:** Nhân vật hành xử nhất quán với tính cách, phát triển hợp lý
3. **drama:** Tình huống gay cấn, hấp dẫn, tạo cảm xúc cho người đọc
4. **writing_quality:** Câu văn hay, rõ ràng, sinh động, giàu hình ảnh

NỘI DUNG CHƯƠNG {chapter_number}:
{content}

BỐI CẢNH TRƯỚC ĐÓ:
{context}

Trả về JSON:
{{"coherence": X, "character_consistency": X, "drama": X, "writing_quality": X, "notes": "nhận xét ngắn gọn về điểm mạnh/yếu"}}"""
