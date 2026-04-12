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
Mỗi nhân vật cần có arc phát triển rõ ràng, xung đột nội tâm, và bí mật.
BẮT BUỘC: Toàn bộ nội dung (tên, tính cách, tiểu sử...) phải viết bằng tiếng Việt.

QUAN TRỌNG: "relationships" PHẢI là một JSON array (danh sách), KHÔNG được là chuỗi text.
Mỗi mối quan hệ là một phần tử riêng trong mảng.

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
      "relationships": ["Là bạn thân của X", "Kẻ thù của Y"],
      "arc_trajectory": "hành trình biến đổi, vd: từ hèn nhát → can đảm",
      "internal_conflict": "xung đột nội tâm cốt lõi",
      "breaking_point": "sự kiện trigger biến đổi",
      "secret": "bí mật sẽ thay đổi dynamics khi bị lộ",
      "speech_pattern": "phong cách nói chuyện đặc trưng"
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
Đảm bảo nhịp điệu: không liên tục climax, xen kẽ setup → rising → climax → cooldown. Mỗi chương thuộc 1 macro arc.
BẮT BUỘC: Viết toàn bộ nội dung (tiêu đề chương, tóm tắt, sự kiện...) bằng tiếng Việt.
BẮT BUỘC: Tên nhân vật PHẢI dùng CHÍNH XÁC như danh sách nhân vật ở trên. Tên địa danh, tông môn PHẢI dùng CHÍNH XÁC như bối cảnh thế giới. KHÔNG được tự ý đổi tên.

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
      "emotional_arc": "cung bậc cảm xúc chương này",
      "pacing_type": "setup/rising/climax/cooldown/twist",
      "arc_id": 1,
      "foreshadowing_plants": ["seed cần gieo trong chương này"],
      "payoff_references": ["seed từ chương trước cần payoff"]
    }}
  ]
}}"""

GENERATE_MACRO_OUTLINE = """Bạn là kiến trúc sư cốt truyện cho truyện {genre}.
Tiêu đề: {title}
Nhân vật: {characters}
Bối cảnh: {world}
Ý tưởng: {idea}
Tổng số chương: {num_chapters}

Hãy chia truyện thành các ARC lớn (mỗi arc khoảng {arc_size} chương).
Mỗi arc phải có xung đột trung tâm riêng, nhân vật trọng tâm, và cách giải quyết.
Các arc phải kết nối logic và escalate stakes qua từng arc.

BẮT BUỘC: Viết toàn bộ bằng tiếng Việt.

Trả về JSON:
{{
  "macro_arcs": [
    {{
      "arc_number": 1,
      "name": "tên arc",
      "chapter_start": 1,
      "chapter_end": 30,
      "central_conflict": "xung đột chính của arc",
      "character_focus": ["nhân vật trọng tâm"],
      "resolution": "arc kết thúc thế nào",
      "emotional_trajectory": "hành trình cảm xúc tổng thể"
    }}
  ]
}}"""

GENERATE_CONFLICT_WEB = """Bạn là chuyên gia xây dựng xung đột cho truyện {genre}.
Tiêu đề: {title}

NHÂN VẬT:
{characters}

CÁC ARC:
{macro_arcs}

Hãy xây dựng MẠNG LƯỚI XUNG ĐỘT phức tạp giữa các nhân vật.
Bao gồm: xung đột bên ngoài (giữa nhân vật), xung đột nội tâm, xung đột tư tưởng.
Mỗi xung đột phải có trigger event và range arc hoạt động.

BẮT BUỘC: Viết toàn bộ bằng tiếng Việt.

Trả về JSON:
{{
  "conflicts": [
    {{
      "conflict_id": "conflict_1",
      "conflict_type": "external/internal/ideological",
      "characters": ["A", "B"],
      "description": "mô tả xung đột",
      "arc_range": "1-3",
      "trigger_event": "sự kiện kích hoạt",
      "status": "dormant"
    }}
  ]
}}"""

GENERATE_FORESHADOWING_PLAN = """Bạn là bậc thầy về foreshadowing và setup-payoff.
Thể loại: {genre}
Tiêu đề: {title}

DÀN Ý TỔNG:
{synopsis}

CÁC ARC:
{macro_arcs}

MẠNG LƯỚI XUNG ĐỘT:
{conflict_web}

Hãy lên kế hoạch FORESHADOWING cho truyện. Mỗi seed phải:
- Được gieo tự nhiên, không lộ liễu
- Có payoff rõ ràng ở chương sau
- Liên quan đến xung đột hoặc bí mật nhân vật

BẮT BUỘC: Viết toàn bộ bằng tiếng Việt.

Trả về JSON:
{{
  "foreshadowing": [
    {{
      "hint": "mô tả seed cần gieo",
      "plant_chapter": 5,
      "payoff_chapter": 25,
      "characters_involved": ["nhân vật liên quan"]
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

CẤU TRÚC MACRO ARC:
{macro_arcs}

MẠNG LƯỚI XUNG ĐỘT:
{conflict_web}

KẾ HOẠCH FORESHADOWING:
{foreshadowing_plan}

TUYẾN TRUYỆN ĐANG MỞ:
{open_threads}

TRẠNG THÁI NHÂN VẬT HIỆN TẠI:
{character_states}

SỰ KIỆN QUAN TRỌNG ĐÃ XẢY RA:
{plot_events}

Hãy tạo dàn ý cho {additional_chapters} chương tiếp theo (bắt đầu từ chương {start_chapter}).
Cốt truyện phải tiếp nối tự nhiên, phát triển xung đột, và tiến tới cao trào.
Đảm bảo nhịp điệu: không liên tục climax, xen kẽ setup → rising → climax → cooldown. Mỗi chương thuộc 1 macro arc.
Phải tận dụng foreshadowing đã gieo để payoff và gieo thêm seed mới cho các chương sau.
Xung đột phải leo thang dựa trên conflict web hiện tại.
BẮT BUỘC: Viết toàn bộ nội dung (tiêu đề chương, tóm tắt, sự kiện, cung bậc cảm xúc...) bằng tiếng Việt. Không được dùng tiếng Anh hay ngôn ngữ khác.
BẮT BUỘC: Tên nhân vật, tông môn, địa danh PHẢI dùng CHÍNH XÁC như danh sách nhân vật và bối cảnh ở trên. KHÔNG được tự ý đổi tên.

Trả về JSON:
{{
  "outlines": [
    {{
      "chapter_number": {start_chapter},
      "title": "tiêu đề chương",
      "summary": "tóm tắt nội dung",
      "key_events": ["sự kiện 1", "sự kiện 2"],
      "characters_involved": ["tên nhân vật"],
      "emotional_arc": "cung bậc cảm xúc chương này",
      "pacing_type": "setup/rising/climax/cooldown/twist",
      "arc_id": 1,
      "foreshadowing_plants": ["seed cần gieo trong chương này"],
      "payoff_references": ["seed từ chương trước cần payoff"]
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

RÀNG BUỘC NHÂN VẬT:
{chars_constraints}

DÀN Ý CHƯƠNG {chapter_number} - {chapter_title}:
{outline}

NỘI DUNG CÁC CHƯƠNG TRƯỚC (tóm tắt):
{previous_summary}

BỐI CẢNH ARC HIỆN TẠI:
{current_arc_context}

THREADS ĐANG MỞ:
{open_threads}

XUNG ĐỘT ĐANG ACTIVE:
{active_conflicts}

FORESHADOWING CẦN GIEO:
{foreshadowing_to_plant}

FORESHADOWING CẦN PAYOFF:
{foreshadowing_to_payoff}

NHỊP ĐỘ CHƯƠNG NÀY: {pacing_type}
{pacing_directive}

YÊU CẦU:
- Viết chương {chapter_number} đầy đủ, khoảng {word_count} từ
- Miêu tả sinh động, đối thoại tự nhiên
- Thể hiện rõ tính cách nhân vật qua hành động và lời nói
- Tạo nhịp điệu kịch tính, có cao trào
- Các sự kiện chính trong DÀN Ý PHẢI xảy ra đầy đủ trong chương này, không được bỏ sót bất kỳ sự kiện nào
- Kết chương tạo sự tò mò cho chương tiếp theo
- Viết hoàn toàn bằng tiếng Việt
- Đối thoại phải reveal tính cách, advance plot, hoặc cả hai — tránh hội thoại trống rỗng
- Mỗi nhân vật nói theo speech pattern riêng
- Subtext quan trọng hơn nói thẳng
- Nếu có foreshadowing cần gieo: gieo tự nhiên, không lộ liễu
- Tuân thủ nhịp độ {pacing_type}: setup=xây dựng nền, rising=tăng căng thẳng, climax=đỉnh điểm, cooldown=nghỉ ngơi phản tỉnh, twist=đảo ngược bất ngờ

TUYỆT ĐỐI TUÂN THỦ TÍNH NHẤT QUÁN TÊN:
- Tên nhân vật PHẢI dùng CHÍNH XÁC như danh sách NHÂN VẬT ở trên. KHÔNG được đổi, viết tắt, phiên âm khác, hay dùng biệt danh trừ khi đã định nghĩa sẵn.
- Tên địa danh, tông môn, bang phái, thế giới PHẢI dùng CHÍNH XÁC như phần BỐI CẢNH THẾ GIỚI ở trên. KHÔNG được tự ý đổi tên hay dùng tên khác.
- Nếu nhân vật cải danh hoặc dùng bí danh, PHẢI giải thích rõ trong nội dung chương (vd: "hắn giấu tên thật, xưng là...").

Bắt đầu viết chương:"""

EXTRACT_STRUCTURED_SUMMARY = """Phân tích chương truyện sau và trích xuất tóm tắt có cấu trúc.

NỘI DUNG CHƯƠNG {chapter_number}:
{content}

THREADS ĐANG MỞ:
{open_threads}

Trả về JSON:
{{
  "plot_critical_events": ["sự kiện ảnh hưởng các chương sau"],
  "character_developments": ["khoảnh khắc phát triển nhân vật"],
  "open_questions": ["câu hỏi người đọc sẽ thắc mắc"],
  "emotional_shift": "cảm xúc thay đổi thế nào trong chương",
  "threads_advanced": ["thread_id đã tiến triển"],
  "threads_opened": ["thread_id mới mở"],
  "threads_resolved": ["thread_id đã giải quyết"],
  "chapter_ending_hook": "khoảnh khắc chưa giải quyết hoặc cliffhanger cuối chương — điều gì khiến người đọc PHẢI đọc tiếp",
  "actual_emotional_arc": "cung bậc cảm xúc THỰC SỰ được truyền tải (ví dụ: 'hy vọng → tuyệt vọng', 'bình lặng → sốc')",
  "brief_summary": "tóm tắt 3-5 câu cho context window"
}}"""

EXTRACT_PLOT_THREADS = """Phân tích chương truyện và xác định các tuyến truyện (plot threads).

NỘI DUNG CHƯƠNG {chapter_number}:
{content}

THREADS ĐANG MỞ TỪ TRƯỚC:
{existing_threads}

Hãy xác định:
1. Threads mới được mở trong chương này
2. Threads cũ được đề cập/tiến triển
3. Threads đã được giải quyết

Trả về JSON:
{{
  "new_threads": [
    {{
      "thread_id": "thread_ch{chapter_number}_1",
      "description": "mô tả tuyến truyện",
      "involved_characters": ["nhân vật liên quan"]
    }}
  ],
  "progressed_threads": ["thread_id đã tiến triển"],
  "resolved_threads": ["thread_id đã giải quyết"]
}}"""

# vi-only
SUMMARIZE_CHAPTER = """Tóm tắt ngắn gọn nội dung chương truyện sau trong 3-5 câu,
tập trung vào sự kiện chính và phát triển nhân vật.
QUAN TRỌNG: Giữ nguyên CHÍNH XÁC tên nhân vật, địa danh, tông môn như trong nội dung gốc. KHÔNG được đổi hay viết khác tên.

{content}"""

EXTRACT_CHARACTER_STATE = """Phân tích chương truyện sau và trích xuất trạng thái hiện tại của từng nhân vật.

NỘI DUNG CHƯƠNG:
{content}

DANH SÁCH NHÂN VẬT CẦN THEO DÕI:
{characters}

QUAN TRỌNG: Tên nhân vật trong "name" PHẢI dùng CHÍNH XÁC như danh sách trên. KHÔNG được đổi hay viết khác tên.
QUAN TRỌNG: Với "relationship_changes", ghi rõ MỐI QUAN HỆ thay đổi thế nào giữa các nhân vật cụ thể.
Ví dụ: "A bắt đầu nghi ngờ B", "C phản bội D", "E và F trở thành đồng minh"

Trả về JSON:
{{
  "character_states": [
    {{
      "name": "tên nhân vật",
      "mood": "tâm trạng hiện tại",
      "arc_position": "rising/crisis/falling/resolution",
      "knowledge": ["điều nhân vật biết được trong chương này"],
      "relationship_changes": ["A bắt đầu nghi ngờ B", "mối quan hệ cụ thể thay đổi"],
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

SCORE_CHAPTER = """Đánh giá chương truyện sau theo 6 tiêu chí (thang điểm 1-5, trong đó 1=rất kém, 3=trung bình, 5=xuất sắc):

1. **coherence:** Cốt truyện logic, mạch lạc, không mâu thuẫn
2. **character_consistency:** Nhân vật hành xử nhất quán với tính cách, phát triển hợp lý
3. **drama:** Tình huống gay cấn, hấp dẫn, tạo cảm xúc cho người đọc
4. **writing_quality:** Câu văn hay, rõ ràng, sinh động, giàu hình ảnh
5. **thematic_alignment:** Chương có củng cố và phát triển chủ đề trung tâm của truyện không
6. **dialogue_depth:** Đối thoại có chiều sâu tâm lý (nói một đằng, ý một nẻo), phân biệt giọng nhân vật

NỘI DUNG CHƯƠNG {chapter_number}:
{content}

BỐI CẢNH TRƯỚC ĐÓ:
{context}

Trả về JSON:
{{"coherence": X, "character_consistency": X, "drama": X, "writing_quality": X, "thematic_alignment": X, "dialogue_depth": X, "notes": "nhận xét ngắn gọn về điểm mạnh/yếu"}}"""
