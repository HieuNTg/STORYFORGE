"""Layer 3 prompts — video storyboard, voice scripts, image generation.

Covers storyboard generation, voice scripting, character/location image
prompt creation.
"""

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
