# Truyện tranh thật sự — Comic Paneling & Dialogue Spec

**Status:** Proposal (planning only — no code yet)
**Date:** 2026-06-09
**Owner:** CTO (Claude) — for CEO review → sprint
**Decision recorded:** Build **full comic pipeline** (Approach **B**), planned in 3 phases.

---

## 0. TL;DR

Hiện tại StoryForge **không tạo truyện tranh** — nó tạo *tranh minh hoạ đơn, mỗi cảnh một tấm*, style "cinematic", tỉ lệ 9:16 toàn trang. Đẹp như bìa sách, nhưng:

- ❌ Không khung (panel) / không gutter / không nhiều khung trên một trang
- ❌ Không bong bóng thoại — **thoại không bao giờ được truyền vào image model** (nửa lời hứa sản phẩm bị bỏ)
- ❌ Không kể chuyện tuần tự, không đa dạng cú máy (mọi tấm đều là "hero shot")
- ❌ Model tự bịa chữ vào ảnh (vd bia đá "KÝ VÕ NGĂN" ở panel04) vì negative prompt bị rơi
- ⚠️ Character consistency mong manh — mặt nhân vật trôi qua các panel

**Giải pháp (Approach B):** Vẽ **1 minh hoạ sạch / beat** (thế mạnh đã có của model) → **ghép trang comic bằng code**: khung + gutter + bong bóng thoại **vector chữ Việt** + thứ tự đọc Z. Chèn thêm tầng **Beat→Shot-list** giữa văn xuôi và vẽ ảnh.

Bản thân image model gần như không đổi — chỉ ngừng hỏi "chân dung hero", bắt đầu hỏi "panel N: cận cảnh Kiên, bên phải khung, nghiêm nghị" — còn *ngôn ngữ truyện tranh* (khung, gutter, bong bóng, thứ tự đọc) được lắp bằng code xung quanh.

---

## 1. Chẩn đoán gốc rễ (có file:line)

| Triệu chứng | Nguyên nhân trong code |
|---|---|
| Mọi tấm là "cinematic single shot" | `image_prompt_style = "cinematic"` hardcode — `data/config.json:40`, default `config/defaults.py:109`, đọc tại `services/media/image_prompt_generator.py:31` |
| Không có khái niệm trang/khung/panel | Template trích cảnh yêu cầu "N cảnh quan trọng nhất", không có "trang"/"khung"/"bố cục" — `services/media/image_prompt_generator.py:11-23` |
| Prompt bị ép về 1 cú máy hero | "Cinematic refiner" viết lại mỗi prompt thành *"ONE cinematic image… [Camera angle]… under 60 words"*, đang BẬT (`flowkit_use_refiner: true`) — `services/media/image_prompt_generator.py:38-71`, gọi tại `services/media/image_generator.py:299-309`. Comment "legacy; ignored" ở `config/defaults.py:142` **SAI** — refiner vẫn chạy. |
| Thoại không vào ảnh | 0 match `dialogue\|speech\|bubble\|thoại` trong `services/media`. Template chỉ trích mô tả hình ảnh; `ImagePrompt` không mang lời thoại; body flowkit chỉ gửi `structuredPrompt.parts[].text` — `services/media/flow_service.py:376-385` |
| Chữ tự bịa trong ảnh | `negative_prompt` được LLM sinh ra (`image_prompt_generator.py:169`) nhưng **không gửi cho flowkit** (chỉ SD dùng — `image_generator.py:197`). Model không bị cấm vẽ text. |
| Wallpaper, không phải trang comic | `flowkit_aspect_ratio = "9:16"` hardcode — `data/config.json:77`, dùng tại `services/media/flow_service.py:69,372-383` |
| Mặt nhân vật trôi | Reference-image chỉ gắn khi `characters_in_scene` khớp tên đã lưu (`image_generator.py:140-147`); lệch tên → rơi về text-only `generate()` (`image_generator.py:149`), không seed pin per-character |

**Live config đang dùng** (`data/config.json`): `image_provider: "flowkit"` (Google Labs Flow / Imagen), `image_prompt_style: "cinematic"`, `panels_per_chapter: 8`, `flowkit_aspect_ratio: "9:16"`, `flowkit_use_refiner: true`.

**Lưu ý quan trọng:** đây KHÔNG phải vấn đề "cheap tier hạ chất lượng ảnh" — chất lượng ảnh xuất sắc. "cheap/layer tier" (commit 977929d) chỉ áp cho LLM viết prompt. Thủ phạm là *nội dung/cấu trúc prompt* + *thiếu hẳn tầng ghép trang & thoại*.

---

## 2. Quality bar — "trang truyện tranh tốt" của StoryForge

### 2.1 Hình học trang
- **Canvas:** 1600 × 2263 px (ISO 1:√2, hợp cả webtoon lẫn in)
- **Lề an toàn:** 60 px; **gutter:** 24–32 px giữa các khung
- **Số khung/trang:** **3–6** cho trang thường; **1** (splash) chỉ cho beat then chốt

### 2.2 Thư viện layout (hữu hạn, chọn theo loại beat)
| Layout | Số khung | Dùng cho |
|---|---|---|
| `SPLASH` | 1 full-bleed | Mở chương, reveal, cao trào |
| `TWO_TIER` | 2 ngang xếp dọc | Thiết lập → phản ứng |
| `THREE_TIER` | 3 ngang xếp dọc | Nhịp hội thoại mặc định |
| `GRID_2x2` | 4 | Trao đổi thoại từng nhịp |
| `BIG_PLUS_TWO` | 1 lớn + 2 nhỏ | 1 khoảnh khắc trội + 2 phụ |
| `SIX_GRID` | 6 (2×3) | Montage / qua lại nhanh |

### 2.3 Luật cú máy & không gian (ép ở tầng shot-list)
- Hai khung liền kề **không** trùng cỡ cảnh. Luân phiên: **EWS** (thiết lập) → **MS** (trung) → **CU** (cận, cảm xúc) → **ECU/insert** → **OTS** (qua vai, hội thoại 2 người).
- **Luật 180°:** trong một cảnh, nhân vật giữ nguyên vị trí trái/phải khung qua các panel.
- **Thứ tự đọc Z (LTR — tiếng Việt chữ Latinh):** panel 1 = trên-trái; bong bóng trong khung cũng trên-trái → dưới-phải. **KHÔNG dùng RTL kiểu manga.**

### 2.4 "Done" cho một trang
1 khung có viền + gutter · ≥2 cỡ cảnh khác nhau · mỗi câu thoại có bong bóng + đuôi chỉ người nói · narration/chuyển cảnh trong hộp caption · thứ tự đọc rõ ràng (Z) · cùng nhân vật nhận ra được qua các khung · chữ Việt đọc được ở bề rộng điện thoại (≥28 px cap-height).

---

## 3. Kiến trúc đích (3 tầng)

```
Văn xuôi chương + thoại
        │
        ▼
┌─────────────────────────┐
│ [MỚI] Beat Extractor     │  LLM: chương → danh sách BEAT (location/speaker/
│      → Shot-list         │  emotional-turn/reveal). Mỗi beat ≈ 1 panel.
│                          │  Gán shot_type, layout/trang, dialogue+speaker.
└─────────────────────────┘
        │  Shot-list JSON (§4.2)
        ▼
┌─────────────────────────┐
│ Image gen (ĐÃ CÓ, sửa)   │  Mỗi panel: prompt comic-panel (KHÔNG text),
│  flowkit/Imagen          │  cỡ cảnh theo shot_type, reference-image nhân vật.
│                          │  → 1 PNG sạch / panel (không bong bóng).
└─────────────────────────┘
        │  panels[] (ảnh) + shot-list (thoại, vị trí người nói)
        ▼
┌─────────────────────────┐
│ [MỚI] Page Compositor    │  Ghép panel vào layout grid + gutter; vẽ bong bóng
│                          │  vector + đuôi; letter thoại Việt; caption box.
│                          │  → trang comic PNG hoàn chỉnh.
└─────────────────────────┘
```

---

## 4. Chi tiết từng phase

### PHASE 1 — Quick win prompt/model (ít rủi ro, đổi ảnh ra ĐÚNG kiểu khung comic ngay)

> Mục tiêu: panel ra dạng khung truyện tranh (cel-shaded, cỡ cảnh đa dạng, không chữ tự bịa) — **dù chưa có bong bóng thoại** (thoại đến ở Phase 3).

Thay đổi (file:line):

1. **Đổi style mặc định** `cinematic` → comic:
   - `data/config.json:40` `image_prompt_style` → `"manhwa comic panel, clean cel shading, bold ink lines"`
   - `config/defaults.py:109` (default tương ứng)
2. **Sửa template trích cảnh** `services/media/image_prompt_generator.py:11-23`:
   - "tạo prompt tiếng Anh cho AI image generation" → **"tạo prompt tiếng Anh cho MỘT KHUNG TRUYỆN TRANH (comic panel)"**
   - Thêm luật: *"Each panel MUST specify a distinct shot type (establishing/wide/medium/close-up/over-the-shoulder/reaction) and vary across the sequence. Render NO text inside the image."*
3. **Sửa/tắt refiner** `services/media/image_prompt_generator.py:50-59`: đổi system prompt thành *"ONE comic-panel prompt: [shot type] + [character action/expression] + [comic art style], explicitly 'no text in image'."* (hoặc `flowkit_use_refiner: false` ở `data/config.json:86`). Sửa luôn comment sai ở `config/defaults.py:142`.
4. **Cắm negative prompt + cấm text vào flowkit** `services/media/flow_service.py:69,376-385`: thêm field negative nếu schema hỗ trợ; nếu không, nối hậu tố cứng vào positive prompt: `"no text, no letters, no watermark, no caption, no speech bubble, no signpost, no logo"`.
5. **Đổi aspect ratio** `flowkit_aspect_ratio` `9:16` → `4:5` (webtoon panel) hoặc `1:1`/`4:3` (grid). Thêm enum vào `_ASPECT_ENUM_MAP` `services/media/flow_service.py:69`.
6. **Fallback reference-image cho consistency** `services/media/image_generator.py:140-149`: khi name-match rỗng, vẫn gắn reference nhân vật chính của chương; cân nhắc seed pin per-character.

Ví dụ prompt (per beat):

```
TRƯỚC:  cinematic, lone hero in ruined village at blood-red dusk, full body,
        dramatic rim light, ultra detailed, 8k, concept art

SAU:    comic book panel, manhwa/webtoon art style, [SHOT: medium close-up],
        {frozen character: Minh — 17yo, short black hair, scar over left brow,
        worn leather tunic}, reacting with shock at the ruined village,
        clean flat cel shading, bold ink outlines, dynamic panel composition,
        NO TEXT, no speech bubbles, no captions, no watermark
```

### PHASE 2 — Tầng Beat→Shot-list (MỚI)

Chèn stage giữa "văn xuôi chương" và "vẽ ảnh".

**Bước 1 — Trích beat:** cắt văn xuôi thành beat. Beat mới bắt đầu khi: đổi địa điểm / người nói mới / bước ngoặt cảm xúc / nhảy thời gian / reveal. Mục tiêu ~1 beat ≈ 1 panel; ~6–10 panel / cặp trang.

**Bước 2 — Shot-list (1 dòng / panel):**

```json
{
  "page": 1,
  "layout": "THREE_TIER",
  "panels": [
    {
      "n": 1,
      "shot": "EWS",
      "beat": "Establish ruined village at blood-dusk",
      "subject": "Kiên",
      "subject_ref": "char_kien_v3",
      "camera": "eye-level, slight low",
      "action": "Kiên stands amid rubble, glowing eye",
      "setting": "ruined village, red sky",
      "mood": "ominous",
      "screen_side": { "Kiên": "center" },
      "captions": [{ "type": "narration", "text": "Làng Đông đã không còn." }],
      "bubbles": []
    },
    {
      "n": 2,
      "shot": "MS",
      "beat": "A survivor pleads",
      "subject": "Bà lão",
      "screen_side": { "Bà lão": "left", "Kiên": "right" },
      "bubbles": [
        { "speaker": "Bà lão", "type": "speech",
          "text": "Cậu... cậu là người sống sót cuối cùng sao?" }
      ]
    },
    {
      "n": 3,
      "shot": "CU",
      "beat": "Kiên's grim resolve",
      "subject": "Kiên",
      "screen_side": { "Kiên": "right" },
      "bubbles": [
        { "speaker": "Kiên", "type": "speech", "text": "Không. Ta là kẻ sẽ báo thù." }
      ]
    }
  ]
}
```

**Bước 3 — luật ép trong extractor:**
- Không hai panel liền kề trùng `shot`.
- Mỗi panel ≤ **2 bong bóng**; nhân vật nói > ~20 từ Việt → tách panel mới.
- Panel đầu của cảnh mới = thiết lập (EWS/WS), kèm caption nếu đổi địa điểm/thời gian.
- Beat lớn nhất chương → `layout: "SPLASH"`.
- Mỗi `subject` trỏ tới một character reference đã lưu (seed + reference image + frozen descriptor).

Tích hợp: stage này nằm trong `services/handlers.py` trước khi gọi `ImageGenerator.generate_story_images`; output shot-list được mang theo tới compositor. `shot`, `dialogue`, `speaker` là field mới — image prompt **không** chứa text; thoại chỉ compositor tiêu thụ.

### PHASE 3 — Page Compositor (MỚI) — mảnh ghép biến "ảnh đẹp" thành "truyện tranh"

**Nhiệm vụ:** nhận `panels[]` (ảnh đã vẽ) + shot-list → vẽ trang comic hoàn chỉnh.

**Công nghệ (Python, server-side):** Pillow (PIL) cho compositing raster; bong bóng vẽ bằng đường cong (ellipse + đuôi polygon) — hoặc render SVG → raster nếu cần bong bóng mượt. Không cần thư viện nặng.

**Pipeline compositor:**
1. Tạo canvas trang (§2.1) theo `layout`.
2. Đặt từng panel vào ô grid; crop/fit theo cỡ cảnh; vẽ viền + gutter.
3. Với mỗi `bubble`: chọn shape theo `type` (§5), đo text wrap (≤18–22 ký tự Việt/dòng), vẽ bong bóng + đuôi chỉ về `screen_side` của `speaker`, đặt ở ~⅓ trên khung, tránh che mặt.
4. Vẽ `caption` (hộp chữ nhật, không đuôi) cho narration/chuyển cảnh.
5. Xuất PNG trang → lưu như "comic page" thay cho panel rời.

**Style guide bong bóng & letter (tiếng Việt):**
- **Font:** phải đủ dấu Việt (`ề ữ ạ ọ ậ ỹ`). Ứng viên: *Be Vietnam Pro* (sạch, hiện đại); font comic (Komika/CC) **chỉ khi** có subset Việt — **test dấu trước khi ship**.
- **Cỡ:** cap-height ≥ 28 px @1600 px; tự co tới sàn rồi mới nới bong bóng.
- **Loại bong bóng:** `speech` (oval, đuôi về miệng) · `thought` (mây, bóng tròn nhỏ) · `shout` (gai) · `whisper` (nét đứt) · `narration` (hộp chữ nhật, không đuôi) · `offscreen` (đuôi ra mép khung).
- **Đặt & đuôi:** chiếm ~⅓ trên khung, không che mặt; thứ tự Z; đuôi chỉ đầu người nói; viền đen 3–4 px + quầng trắng để nổi trên nền tối (panel08); tối đa 2 bong bóng/khung.
- **Caption Việt:** "Làng Đông — hoàng hôn", "Ba ngày sau." — ngắn gọn.

---

## 5. Thay đổi data model

- `ImagePrompt` (`services/media/image_prompt_generator.py`): thêm `shot_type`, `dialogue: list[{speaker, type, text}]`, `screen_side: dict`.
- Đầu ra chương: lưu **comic page** (trang đã ghép) song song panel rời; FE `chapter_images` trỏ tới trang ghép. Cần kiểm `frontend/lib/api/illustration.ts` (`chapter_images`) + UI reader render trang thay panel.
- Config mới: `comic_layout_mode`, `comic_page_canvas`, `comic_font`, bật/tắt compositor (để A/B với output cũ).

---

## 6. Danh sách file cần đụng (tổng hợp)

| File | Phase | Việc |
|---|---|---|
| `data/config.json` / `config/defaults.py` | 1 | style→comic, aspect ratio, sửa comment refiner, config compositor mới |
| `services/media/image_prompt_generator.py` | 1,2 | template comic-panel; refiner→comic; thêm field shot/dialogue/speaker |
| `services/media/flow_service.py` | 1 | enum aspect mới; cắm negative/cấm-text |
| `services/media/image_generator.py` | 1 | fallback reference-image; (tuỳ) seed pin |
| `services/handlers.py` | 2 | chèn stage Beat→Shot-list trước generate_story_images |
| **MỚI** `services/media/shot_list.py` | 2 | beat extractor → shot-list (LLM + luật) |
| **MỚI** `services/media/page_compositor.py` | 3 | ghép trang + bong bóng + letter |
| **MỚI** `assets/fonts/` | 3 | font Việt comic (Be Vietnam Pro) |
| `frontend/lib/api/illustration.ts` + reader UI | 3 | render trang ghép thay panel rời |

---

## 7. Test
- **Phase 1:** snapshot prompt builder → khẳng định prompt chứa "comic panel", "NO TEXT", shot_type; refiner output không "cinematic". Kiểm flowkit body có hậu tố cấm-text + aspect mới.
- **Phase 2:** unit cho shot_list: không 2 shot liền kề trùng; ≤2 bubble/panel; cảnh mới mở bằng EWS/WS; SPLASH gán đúng beat lớn nhất; thoại Việt round-trip nguyên vẹn.
- **Phase 3:** golden-image test compositor (layout cố định, seed cố định) → so pixel/perceptual hash; test wrap chữ Việt có dấu; test đuôi bong bóng chỉ đúng `screen_side`; test tương phản chữ trên nền tối.

---

## 8. Trình tự khuyến nghị
1. **Phase 1** trước (1 ngày, ít rủi ro) — ảnh ra đúng kiểu khung comic ngay, CEO thấy khác biệt liền.
2. **Phase 2** (shot-list) — nền tảng cho thoại + bố cục.
3. **Phase 3** (compositor) — biến thành truyện tranh đúng nghĩa với bong bóng thoại Việt.

Mỗi phase độc lập deploy được; bật/tắt compositor qua config để A/B với output cũ và rollback an toàn.
