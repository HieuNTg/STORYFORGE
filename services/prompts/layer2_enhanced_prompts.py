"""Prompt templates cho Layer 2 nâng cao — Psychology Engine và các tính năng mới."""

EXTRACT_PSYCHOLOGY = """Phân tích tâm lý sâu của nhân vật sau:

TÊN: {name}
TÍNH CÁCH: {personality}
TIỂU SỬ: {background}
ĐỘNG LỰC: {motivation}
BÍ MẬT: {secret}
MÂU THUẪN NỘI TÂM: {internal_conflict}
ĐIỂM GÃY: {breaking_point}

CÁC NHÂN VẬT KHÁC: {other_characters}

Trả về JSON:
{{
  "primary_goal": "mục tiêu chính",
  "hidden_motive": "động cơ ẩn giấu",
  "fear": "nỗi sợ sâu nhất",
  "shame_trigger": "điều khiến nhân vật xấu hổ/mất kiểm soát",
  "vulnerabilities": [
    {{"wound": "vết thương tâm lý", "exploiters": ["tên nhân vật có thể khai thác"], "drama_multiplier": 2.0}}
  ],
  "defenses": ["cơ chế phòng vệ: phủ nhận/tấn công/rút lui/..."]
}}"""

# --- Scene Enhancement prompts ---

DECOMPOSE_CHAPTER_CONTENT = """Chia nội dung chương sau thành 3-5 cảnh riêng biệt.
Mỗi cảnh là một đơn vị hành động/đối thoại có ranh giới rõ ràng.

NỘI DUNG CHƯƠNG:
{content}

Trả về JSON:
{{
  "scenes": [
    {{
      "scene_number": 1,
      "content": "nội dung đầy đủ của cảnh",
      "characters_present": ["tên nhân vật"]
    }}
  ]
}}"""

SCORE_SCENE_DRAMA = """Đánh giá kịch tính của cảnh sau (thang 0-1).

THỂ LOẠI: {genre}

NỘI DUNG CẢNH:
{content}

Tiêu chí: xung đột, căng thẳng, cảm xúc mạnh, bước ngoặt, đối thoại sắc bén.

Trả về JSON:
{{
  "drama_score": 0.7,
  "weak_points": ["điểm yếu cụ thể"],
  "strong_points": ["điểm mạnh cụ thể"]
}}"""

ENHANCE_SCENE = """Viết lại cảnh sau để tăng kịch tính. Giữ nguyên nhân vật và sự kiện chính.

THỂ LOẠI: {genre}
ĐIỂM YẾU CẦN SỬA: {weak_points}
SỰ KIỆN LIÊN QUAN: {events}
HƯỚNG DẪN ĐỐI THOẠI: {subtext_guidance}
HƯỚNG DẪN CHỦ ĐỀ: {thematic_guidance}

NỘI DUNG GỐC:
{content}

Yêu cầu: thêm căng thẳng, đối thoại sắc bén có chiều sâu tâm lý, cảm xúc mạnh hơn.
Viết hoàn toàn bằng tiếng Việt."""

# --- Dialogue Subtext prompt ---

DIALOGUE_SUBTEXT_GUIDANCE = """Phân tích đối thoại trong đoạn văn sau. Với MỖI câu thoại quan trọng, chỉ ra:

NỘI DUNG:
{content}

NHÂN VẬT VÀ TÂM LÝ:
{character_psychology}

KIẾN THỨC CỦA TỪNG NHÂN VẬT:
{knowledge_state}

Trả về JSON:
{{
  "dialogue_analysis": [
    {{
      "character": "tên",
      "says": "câu nói nguyên văn",
      "means": "ý nghĩa thực sự / điều muốn đạt được",
      "subtext_type": "deflection/half_truth/loaded_silence/misdirection/genuine",
      "tension_contribution": 0.7
    }}
  ],
  "enhancement_guidance": "hướng dẫn cụ thể để cải thiện đối thoại: thêm im lặng đầy ý nghĩa, lời nói nửa vời, né tránh..."
}}"""

# --- Thematic Resonance prompts ---

EXTRACT_THEME = """Phân tích chủ đề trung tâm của truyện sau:

TIÊU ĐỀ: {title}
THỂ LOẠI: {genre}
TÓM TẮT: {synopsis}
TIỀN ĐỀ CHỦ ĐỀ: {premise}

NHÂN VẬT:
{characters}

Trả về JSON:
{{
  "central_theme": "chủ đề trung tâm (1 câu ngắn gọn)",
  "recurring_motifs": ["hình ảnh/biểu tượng lặp lại trong truyện"],
  "symbolic_items": ["vật thể mang ý nghĩa biểu tượng"],
  "thematic_questions": ["câu hỏi chủ đề truyện đặt ra cho người đọc"]
}}"""

SCORE_CHAPTER_THEME = """Đánh giá mức độ chương này củng cố chủ đề trung tâm.

CHỦ ĐỀ: {central_theme}
MOTIF CẦN CÓ: {motifs}
BIỂU TƯỢNG: {symbols}

NỘI DUNG CHƯƠNG:
{content}

Trả về JSON:
{{
  "theme_alignment": 0.7,
  "motifs_present": ["motif đã xuất hiện trong chương"],
  "motifs_missing": ["motif nên thêm vào để củng cố chủ đề"],
  "drift_warning": "cảnh báo nếu chương lệch chủ đề (để rỗng nếu ổn)"
}}"""
