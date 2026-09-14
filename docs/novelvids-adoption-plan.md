# Batch L — Đưa phần quản lý thực thể và cắt phân cảnh của novelvids vào STORYFORGE

Trạng thái: **Plan — chờ CEO duyệt, chưa viết code.**
Đầu vào: bản đánh giá "Nên đưa gì từ novelvids vào STORYFORGE" (2026-09-14).
Checklist thực thi: `IMPLEMENTATION_PLAN.md` → Batch L.

Tài liệu này không chép lại bản đánh giá. Nó ghi lại những gì đã đối chiếu với code trên `master` (`4c0bb1e`), những chỗ bản đánh giá đúng, những chỗ lệch, và plan được sửa theo đó.

---

## 1. Đối chiếu bản đánh giá với code

| # | Bản đánh giá nói | Code thật | Kết luận |
| --- | --- | --- | --- |
| 1 | `Character` chỉ có `name` | `models/schemas.py:17`. Không có khái niệm alias nào trong `models/`, `pipeline/`, `services/` | **Đúng** |
| 1 | Registry so khớp nguyên tên | `character_state_registry.py:66-69`, và cùng kiểu ở `:247`, `:307` | **Đúng, còn rộng hơn**: 3 chỗ, không phải 1. Đây là so khớp chuỗi con nên còn báo nhầm (tên ngắn nằm trong từ khác) |
| 1 | Dialogue checker xác định người nói bằng tên đầy đủ | `dialogue_consistency_checker.py:30-45` | **Đúng** |
| 1 | Shot list lấy ảnh tham chiếu bằng `refs.get(panel.subject)` | `shot_list.py:438`. `refs` có key là `c.name` (`handlers.py:313-329`) | **Đúng** |
| 1 | *(bản đánh giá không nhắc)* | `consistency_validators.validate_character_names` (`:95-142`) chỉ coi tên đầy đủ, tên gọi, và họ + tên là hợp lệ. `_is_name_variant` báo mọi nhóm từ viết hoa **chứa** tên và dài hơn 1–3 ký tự | **Lỗ hổng nặng nhất, bản đánh giá bỏ sót.** "Long Ca" của nhân vật "Trần Long" bị báo "Có thể sai tên". Cảnh báo này đi vào `repair/collector._name_findings` và **được chấm điểm** trong Batch K, nên repair loop có thể viết lại chương để "sửa" một tên gọi đúng |
| 1 | Chương gọi "hắn" thì nhân vật bị coi là vắng mặt | Đúng về triệu chứng | **Alias không sửa được đại từ.** "hắn", "nàng", "y" không có ánh xạ tất định. Alias chỉ gỡ được tên gọi và danh xưng ("Long ca", "thiếu gia"). Đại từ cần nguồn khác, xem L1.5 |
| 1 | "LLM trả về tên gọi mới sau mỗi chương" | `post_processing.py:136` đã gọi `extract_character_states` **mỗi chương**, dùng model rẻ, prompt đọc cả chương | **Không cần thêm call.** Ghép trường `aliases_used` vào prompt có sẵn |
| 2 | `content[:8000]` | `shot_list.py:628` và `:713` dùng chung `CONTENT_WINDOW = 8000` (ký tự) | **Đúng, và xảy ra ngay với cấu hình mặc định.** Chương 2.000 từ tiếng Việt vào khoảng 9–11 nghìn ký tự, nên phần cuối chương thường không có panel. Bước kiểm độ phủ không bắt được vì nó cũng chỉ thấy 8000 ký tự đầu |
| 3 | `_close_truncated_json` vá JSON bị cắt nên mất panel âm thầm | `generation.py:510-512`: chỉ chạy khi JSON **không có dấu đóng ngoặc nào**. JSON shot list bị cắt gần như luôn còn `}` của panel trước | **Sai đường đi.** Đường mất dữ liệu thật: parse lỗi → `_repair_json` cắt tới `}` cuối → vẫn lỗi → **nhờ LLM sửa nhưng chỉ gửi `text[:4000]`** (`generation.py:175`). Model sửa trả về một JSON hợp lệ nhưng ngắn hơn, và **mọi** caller của `generate_json` đều dính, không chỉ shot list |
| 3 | Phát hiện bằng `finish_reason == "length"` | Provider `complete()` chỉ trả `str` (`openai_provider.py:108-114`). Proxy Gemini-API mà CEO đang dùng **luôn** trả `finish_reason="stop"` (`Gemini-API/server/main.py:205,240`) | **Không dùng được trên provider thật.** Phải phát hiện bị cắt một cách tất định: parse lỗi và ngoặc chưa đóng khi quét có xét chuỗi |
| 3 | `shot_list.py:654` bắt mọi exception rồi trả rỗng | Đúng. Docstring ghi rõ đây là chủ ý: lùi về đường sinh ảnh cũ | **Giữ việc lùi, bỏ sự im lặng**: ghi lý do và đếm lại |
| 4 | Một `frozen_prompt` và một `outfit.default` | `character_visual_profile.py:86-117`, `_visual_extractor_prompts.py:15` | **Đúng** |
| 4 | `physical_state` có sẵn, chỉ cần nối sang | `physical_state` chỉ có trong `CharacterStateRegistry` của **L2**, nằm trong bộ nhớ của `ConsistencyEngine`, không lưu cùng truyện. Comic sinh **theo yêu cầu, sau đó**, từ Library (`/api/images/...`) | **Không "chỉ cần nối".** Lúc vẽ không còn dữ liệu đó. Hơn nữa `physical_state` gộp cả trạng thái tạm thời ("mệt mỏi"), không phải cái nào cũng đổi hình thái |
| 5 | Dùng `characters_involved` dự kiến | `tiered_context_builder.py:159` lấy từ outline, và `:168` lấy từ `structured_summary.character_developments` | **Đúng.** Tùy chọn |
| — | Phần "không nên chép" | `setting_continuity.py:14,25,32` có `Location`, `SignificantObject.current_owner`. `voice_fingerprint.py`, `character_voice_profiler.py` có tồn tại | **Đồng ý** |

---

## 2. Thứ tự và lý do

Bản đánh giá đề xuất 1 → 3 → 2 → 4. Plan này làm **L0 → L1 → L2 (gộp mục 2 và 3) → L3 → L4 (tùy chọn)**.

- **L0 đo trước khi làm.** Mọi con số "thường xuyên" trong bản đánh giá là suy luận. Một script tất định chạy trên truyện có sẵn sẽ trả lời ba câu, không tốn call LLM nào:
  - Bao nhiêu `name_warnings` là tên gọi hợp lệ.
  - Bao nhiêu chương dài hơn 8000 ký tự.
  - Bao nhiêu panel có `subject` không khớp `refs`.

  Đo xong mới biết L1 và L2 đáng bao nhiêu công.
- **L1 lên đầu, và gấp hơn bản đánh giá nghĩ.** Batch K đã merge và đang bật mặc định. Báo nhầm tên đang là nguồn finding được chấm điểm trong repair loop, nên chỗ này có thể **gây ra** việc viết lại chương sai, không chỉ bỏ sót.
- **Gộp mục 2 và 3.** Bước "chia đôi rồi gọi lại" của mục 3 cần đúng bộ cắt theo đoạn văn của mục 2. Làm mục 3 trước thì phải dựng bộ cắt hai lần. Cắt theo đoạn cũng khiến việc bị cắt cụt hiếm đi, nên đường chia đôi thành đường dự phòng.
- **Lỗi fixer `text[:4000]` tách ra một mục riêng trong L2.** Lỗi này ở `generate_json`, dùng chung cho mọi caller. Cách sửa hẹp: text quá dài thì ném lỗi, không gửi bản bị cắt đi sửa. Mọi caller vốn đã bắt exception, nên chỉ đổi "dữ liệu thiếu mà im lặng" thành "lỗi có tên".
- **L3 (hình thái) lớn hơn bản đánh giá nói** vì thiếu nguồn dữ liệu lưu cùng truyện. Có một quyết định sản phẩm cần CEO chốt, xem §4.

---

## 3. Chi tiết từng bước

Luật chung, lấy từ CLAUDE.md:
- Chạy Serena `find_referencing_symbols` trước khi sửa mọi symbol dùng chung.
- Mỗi lỗi đi kèm một regression test, và test đó phải fail trên code trước khi sửa.
- Không thêm `getattr(config, "x", default)`. Config mới chỉ khai báo ở `config/defaults.py`.
- Verifier luôn tất định, không bao giờ để LLM làm judge.

### L0. Đo nền (không tốn call LLM)

Viết `scripts/measure_entity_gaps.py`, đọc checkpoint hoặc truyện đã sinh, và in ra:
1. Với mỗi chương: số `validate_character_names` báo, liệt kê các nhóm từ chứa tên nhân vật. CEO hoặc CTO gắn nhãn tay cho khoảng 20 mẫu: tên gọi hợp lệ hay viết sai thật.
2. Phân bố `len(chapter.content)` so với `CONTENT_WINDOW`, tức phần trăm chương bị cắt và số ký tự mất.
3. Với truyện đã có comic: phần trăm panel có `subject_ref` rỗng dù `subject` không rỗng.

Tiêu chí tiếp tục:
- L1 đáng làm nếu ≥ 1 trong 5 cảnh báo tên là báo nhầm, **hoặc** ≥ 10% panel có subject mà không có ảnh tham chiếu.
- L2 đáng làm nếu ≥ 20% chương dài hơn cửa sổ.
- Không đạt thì ghi số vào plan rồi hạ ưu tiên.

### L1. Bảng alias cho nhân vật

**Dữ liệu**
- `Character.aliases: list[str] = []`. Có giá trị mặc định nên truyện đã lưu (Library ở localStorage, checkpoint) vẫn nạp được.

**Resolver**, đặt ở `services/character_names.py`. Không đặt trong `pipeline/`, vì `services/media/shot_list.py` cũng dùng và không nên import ngược từ pipeline.
- `build_name_index(characters) -> NameIndex`. Chuẩn hóa bằng Unicode NFC, casefold, bỏ dấu câu hai đầu. Tên đầy đủ, tên gọi và mọi alias đều trỏ về tên chuẩn. Một alias trỏ tới **hai** nhân vật thì bị đánh dấu mơ hồ.
- `resolve_character(text, index) -> str | None`. Chỉ khớp chính xác sau chuẩn hóa, **không khớp mờ**. Alias mơ hồ trả về `None`.
- `mentions(content, character, index) -> bool`. Khớp theo ranh giới từ (regex Unicode), để bỏ kiểu báo nhầm chuỗi con của `name.lower() in content.lower()`.

**Tìm alias**, không thêm call LLM:
- Thêm trường `"aliases_used": [...]` cho mỗi nhân vật trong `EXTRACT_CHARACTER_STATE` (`services/prompts/story_prompts.py:388`).
- Gộp vào `Character.aliases` trên luồng gọi, trong `post_processing.py` (cùng chỗ Batch K đọc kết quả), chỉ khi **tất cả** điều kiện tất định sau đúng:
  - Chuỗi xuất hiện **nguyên văn** trong chương. Kiểm lời LLM bằng văn bản, không tin LLM.
  - Không trùng tên chuẩn.
  - Không nằm trong danh sách đại từ và từ xưng hô chung ("hắn", "nàng", "y", "gã", "lão", "cô ấy", "anh ấy", "ta", "ngươi", ...).
  - Dài ≥ 2 ký tự.
  - Không phải tên chuẩn hay alias của nhân vật khác. Trùng thì ghi vào danh sách mơ hồ, không gộp.

**Thay 6 chỗ so khớp.** Mỗi chỗ chạy `find_referencing_symbols` trước.
1. `character_state_registry.py:66-69`, `:247`, `:307`: đổi sang `mentions`.
2. `dialogue_consistency_checker.py:30-45`: xác định người nói qua index.
3. `shot_list.py:438`: `refs.get(resolve_character(panel.subject) or panel.subject)`. Làm tương tự cho `bubble.speaker`.
4. `consistency_validators.validate_character_names`: `valid_forms` thêm alias. Vẫn báo lỗi viết sai thật.
5. `consistency_validators.py:225` (kiểm chuyển cảnh): đổi sang `mentions`.
6. Sinh prompt cho nhân vật (`chapter_writer`) liệt kê alias, để model viết đúng tên gọi đã có.

**Regression test**, mỗi test fail trên `master` hiện tại:
- `test_alias_not_flagged_as_misspelling`: "Long Ca" đã đăng ký thì không có cảnh báo; "Trần Lonng" vẫn bị báo.
- `test_repair_loop_ignores_registered_alias`: chạy `collect_findings` / `recheck_findings` trên chương chỉ dùng alias thì không ra finding nguồn `name`. Đây là test khóa tương tác với Batch K.
- `test_registry_detects_alias_only_presence`.
- `test_dialogue_attributed_via_alias`.
- `test_shot_list_subject_alias_gets_reference`.
- `test_ambiguous_alias_resolves_none`.
- `test_alias_merge_rejects_pronoun_and_unseen_text`: LLM khai "hắn", hoặc khai một chuỗi không có trong chương, thì không được gộp.
- `test_mentions_word_boundary`: tên ngắn không khớp bên trong từ khác.

**L1.5 (ghi nhận, chưa làm).** Chương chỉ dùng đại từ vẫn bị registry coi là vắng mặt. Cách rẻ nhất: coi nhân vật có mặt nếu `mentions` đúng **hoặc** tên nằm trong `outline.characters_involved`. Cách này đổi chữ ký `extract_states_from_chapter`, nên cần đo L0 trước.

### L2. Shot list: cắt theo đoạn, mang panel trước sang, chia đôi khi bị cắt cụt

**L2a. Fixer không được sửa bản đã bị cắt**

Lỗi này **đã gây mất dữ liệu thật** trong smoke run Batch K ngày 2026-09-14:
- Người dùng yêu cầu 5 chương, pipeline chỉ viết 2 chương mà vẫn báo "Layer 1 hoàn tất".
- `revise_outline_from_critique` nhận về 18.871 token completion trong 558s. JSON trong đó có xuống dòng thô bên trong chuỗi (`Invalid control character`).
- `_repair_json` không sửa được lỗi này, nên fixer chỉ nhận `text[:4000]`.
- `gemini-3.1-flash-lite` trả về một JSON hợp lệ có 2 chương, và dàn ý 2 chương đó được nhận.
- Lượt legacy chạy cùng ý tưởng vẫn giữ đủ 5 chương.

Việc cần làm:
- **Bước 0, không tốn call:** thử `json.loads(text, strict=False)` trước `_repair_json`. `strict=False` chấp nhận ký tự điều khiển trong chuỗi, tức đúng lỗi của lần chạy trên.
- Ở `generation.py:159-179`: khi `len(text) > 4000`, **không** gọi fixer, mà ném `ValueError` có nói rõ độ dài.
- Test:
  - `test_json_fixer_never_receives_truncated_text`: JSON lỗi dài 6000 ký tự thì ném lỗi, và fake fixer không bị gọi. Trên `master`, test này fail vì fixer được gọi và trả về JSON ngắn hơn.
  - `test_raw_newline_in_string_parses_without_llm`.
- Chạy `find_referencing_symbols` trên `generate_json`. Đây là symbol dùng rộng nhất trong cả batch.
- Lỗi thiếu kiểm số chương của outline critic được ghi riêng ở `IMPLEMENTATION_PLAN.md` Batch J. Đó là lỗi P0, không chờ Batch L.

**L2b. Cắt chương**
- `_chunk_by_paragraph(content, budget=CONTENT_WINDOW)`: cắt ở `\n\n`, rồi `\n`. Nếu một đoạn vẫn dài hơn budget thì cắt ở ranh giới câu.
- Số panel mỗi chunk tỉ lệ với độ dài chunk, tối thiểu 1, và tổng vẫn bằng `num_panels`.
- Các chunk trong **một** chương chạy tuần tự, vì cần panel trước. Các chương vẫn chạy song song như commit `18b9ec0`.
- Prompt của chunk thứ k > 1 nhận:
  - Panel cuối của chunk trước, dạng JSON rút gọn: `subject`, `setting`, `screen_side`, `action`, `mood`.
  - Số `n` bắt đầu.
- Bước kiểm độ phủ (`_repair_coverage`) chạy **trên từng chunk**, với đúng văn bản của chunk đó. Như vậy độ phủ nhìn thấy cả chương.
- Gộp panel, đánh số lại, rồi chạy `enforce_rules` **một lần** trên cả chương, vì `_merge_to_budget` và SPLASH cần thấy toàn bộ.

**L2c. Bị cắt cụt thì chia đôi**
- Shot list gọi `llm.generate(..., json_mode=True)` rồi tự parse. Không đi qua đường sửa của `generate_json`, vì đường đó được viết cho JSON hỏng chứ không cho JSON thiếu.
- Cách phát hiện bị cắt (tất định): `json.loads` lỗi **và** khi quét có xét chuỗi thì còn ngoặc chưa đóng hoặc chuỗi chưa đóng.
  - JSON bị cắt: chia chunk đôi ở ranh giới đoạn hoặc câu gần giữa nhất, rồi gọi lại. Giới hạn độ sâu 3 và độ dài chunk tối thiểu 800 ký tự. Vượt giới hạn thì ném lỗi.
  - JSON hỏng nhưng không bị cắt: dùng `_repair_json` như hiện nay.
- `shot_list.py:654` giữ việc lùi về `ShotList` rỗng, nhưng ghi `logger.error` kèm lý do (`truncated_unsplittable`, `parse_error`, ...), và đếm vào `trace` nếu có.

**Regression test**
- `test_long_chapter_every_paragraph_reaches_llm`: chương 20.000 ký tự thì mọi đoạn đều nằm trong ít nhất một prompt. Trên `master` fail, vì phần sau ký tự 8000 không bao giờ tới LLM.
- `test_coverage_check_sees_chapter_tail`.
- `test_truncated_response_splits_and_keeps_both_halves`.
- `test_unsplittable_truncation_raises_then_degrades`.
- `test_panel_numbering_continuous_across_chunks`.
- `test_second_chunk_prompt_carries_previous_panel`.
- `test_short_chapter_single_call_unchanged`: chương ngắn hơn cửa sổ vẫn đúng 1 call như cũ, không tăng chi phí.

**Chi phí:** chương dài hơn 8000 ký tự tốn k call thay vì 1, cộng k call kiểm độ phủ nếu bật. Với chương mặc định 2.000 từ thì k ≈ 2. Đây là call model rẻ, và là cái giá để phần cuối chương có panel.

### L3. Hình thái nhân vật cho ảnh (chờ quyết định §4)

**Dữ liệu**, lưu cùng truyện:
- `Character.forms: list[CharacterForm] = []`.
- `CharacterForm = {key, from_chapter, description, frozen_prompt, reference_image}`.
- Hình thái gốc là trạng thái hiện tại, không cần một bản ghi riêng.

**Nguồn**, không thêm call LLM:
- Thêm trường `"visual_change": {"persistent": bool, "description": str}` vào cùng prompt `EXTRACT_CHARACTER_STATE` của L1.
- Chỉ `persistent=true` mới tạo form mới. Ví dụ tạo form: đổi đạo bào, mất một tay, sẹo, tóc bạc sau khi thức tỉnh. Ví dụ không tạo: mệt, dính máu, ướt mưa.
- Kiểm tất định trước khi nhận: `description` phải chứa ít nhất một cụm từ xuất hiện trong chương.

**Chọn form lúc vẽ chương N:** lấy form có `from_chapter` lớn nhất nhưng không vượt N. Gắn vào `handlers.py:313-329`, nơi đang dựng `character_references`, và vào `get_frozen_prompt`.

**Ảnh tham chiếu cho form** (quyết định §4):
- Phương án A: chỉ đổi prompt, dùng lại ảnh tham chiếu gốc.
- Phương án B: tạo ảnh tham chiếu mới bằng cách sửa ảnh gốc qua `qwen-local` `/v1/images/qwen/edits`, provider duy nhất sửa được ảnh. Nếu hết quota thì lùi về A.

**Regression test**
- `test_form_selection_by_chapter`.
- `test_transient_state_does_not_create_form`.
- `test_form_description_must_be_grounded_in_text`.
- `test_old_story_without_forms_renders_as_before`.

### L4. `appearances` (tùy chọn, sau L1)

- `Character.appearances: list[int]`, tính tất định bằng `mentions` trong `post_processing`.
- Dùng cho:
  - `tiered_context_builder._promote` (`:157`): thay dự kiến ở `:159` bằng số liệu thật.
  - Một cảnh báo "nhân vật chính vắng mặt ≥ K chương".
- Chỉ làm khi L0 hoặc L1 cho thấy việc promote sai ngữ cảnh gây lỗi thật.

---

## 4. Quyết định cần CEO

1. **Duyệt thứ tự L0 → L1 → L2 → L3**, trong đó mục 2 và 3 gộp làm một, và lỗi fixer `text[:4000]` được sửa ở `generate_json` chung. Đây là chỗ khác với bản đánh giá.
2. **L3, ảnh tham chiếu cho hình thái:**
   - **A:** chỉ đổi prompt. Không tốn quota ảnh, nhưng giữ khuôn mặt yếu hơn.
   - **B:** sửa ảnh gốc qua qwen-local. Giữ mặt tốt hơn, nhưng tốn khoảng 40s và 1 lượt quota ảnh Qwen/ngày cho mỗi form.

   Đề xuất: **B, lùi về A** khi hết quota.
3. **L1.5 (xử lý đại từ):** đo L0 xong mới quyết.

## 5. Không làm

Đồng ý với bản đánh giá, và đã kiểm lại:
- Cú pháp `@{Tên}`.
- Chiến lược "điện ảnh / lời kể".
- Bảng Scene nhiều-nhiều.
- Video, nối khung cuối, pipeline Remake.
- Kho địa điểm và vật phẩm.

Thêm:
- **Không** khớp tên mờ trong resolver. Khớp mờ là việc của detector viết sai, không phải của phép nhận diện.
- **Không** thêm call LLM riêng để tìm alias hay hình thái.

---

## 6. Kết quả L0 (2026-09-14) và điều chỉnh plan

CEO đã duyệt thứ tự và phương án B (lùi về A) cho L3. L0 đã chạy trên 5 truyện thật (8 văn bản, 24 chương) bằng `scripts/measure_entity_gaps.py`.

**Cảnh báo tên sai: 18/18 là báo nhầm, không có ca nào là alias.** Gắn nhãn tay từng ca, xem ngữ cảnh trong văn bản:

| Nguyên nhân | Số ca | Ví dụ nguyên văn |
| --- | --- | --- |
| Nhóm chữ viết hoa bị nối xuyên dấu câu | 13 | `"Ai?" Lâm Phong` → "Ai Lâm Phong"; `Dạ Sát.⏎⏎"Kẻ` → "Dạ Sát Kẻ"; `Vân Tuyết Dao. Đó` |
| Từ đầu câu bị so khoảng cách chỉnh sửa với tên gọi ngắn | 5 | "Thân là rồng…" ~ "Chân"; "Ông ho…" ~ "Không" |
| Alias hay danh xưng thật | **0** | — |
| Tên viết sai thật | **0** | — |

Ca "Hạnh Cô" trong smoke run cũng nhiều khả năng cùng nguyên nhân nối qua dấu câu. Bản cuối của chương đã được viết lại nên không còn văn bản để kiểm.

**Hệ quả đối với plan**
- Giả định của bản đánh giá, và của plan này ở §1, rằng "alias là nguồn báo nhầm" **không đúng với dữ liệu**. Lỗi thật là bước tách từ của detector.
- Lỗi đó đã sửa (L1'). Trên dữ liệu thật, số cảnh báo giảm từ **18 xuống 2**, và detector vẫn bắt tên viết sai ở giữa câu, sau dấu câu, và ở đầu câu.
- Nhân vật chỉ được gọi bằng một phần tên: 1 lần trong 24 chương. Truyện hiện đại của smoke run vẫn nhắc tên đầy đủ ít nhất một lần mỗi chương. **Bảng alias hoãn** cho tới khi có truyện cụ thể bị lỗi vì tên gọi.
- Chương dài hơn `CONTENT_WINDOW`: 8% trên dữ liệu cũ, dưới ngưỡng 20%. Nhưng chương 1 của smoke run (cấu hình hiện tại) dài 11.892 ký tự. L2b/L2c chờ số đo trên truyện legacy 5 chương. L2a đã làm cùng lỗi P0.
