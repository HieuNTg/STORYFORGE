# ChatGPT → Web API: Blueprint học từ `gemini-webapi`

> Mục tiêu: giữ đường **ChatGPT free (session đăng nhập của user)**, nhưng thay vì relay qua extension FlowKit, áp **kiến trúc "web app → web API sạch"** mà `HanaokaYuzu/Gemini-API` (`gemini-webapi`) đã chứng minh chạy được. Tài liệu này bóc tách pattern đó thành các tầng, map từng tầng sang ChatGPT, và chỉ rõ **một tầng duy nhất không bê thẳng được** (Sentinel proof-of-work) cùng cách xử lý.

Tham chiếu nguồn: `C:\Users\Admin\OneDrive\Desktop\Gemini-API` (gemini-webapi + `server/`).
Liên quan: `docs/chatgpt-image-flowkit-spec.md` (chi tiết protocol ChatGPT đã research), `docs/flowkit-integration.md`.

---

## 1. Pattern "web app → web API" mà gemini-webapi dạy (6 tầng)

`gemini-webapi` biến gemini.google.com (không có API công khai) thành một **server tương thích OpenAI** chạy local, **không cần extension, không cần browser**. Nó làm được nhờ 6 tầng xếp chồng:

| # | Tầng | gemini-webapi làm gì | File nguồn |
|---|------|----------------------|-----------|
| 1 | **TLS impersonation** | Dùng `curl_cffi` với `AsyncSession(impersonate="chrome")` → giả vân tay TLS/JA3 của Chrome thật, vượt bot-detection của Cloudflare/Google **mà không cần browser** | `utils/get_access_token.py:74-76` |
| 2 | **Session = cookie + scrape in-page token** | Nạp cookie `__Secure-1PSID` / `-1PSIDTS`, GET trang `/app`, **regex bới token `SNlM0e`** ra khỏi HTML | `get_access_token.py:271-289` (`re.search(r'"SNlM0e":\s*"(.*?)"', html)`) |
| 3 | **Tự xoay session nền** | Background task POST endpoint `rotate_cookies` mỗi N giây để làm tươi `-1PSIDTS`, cache ra đĩa, chống hết hạn → "always-on" | `utils/rotate_1psidts.py:49-106` |
| 4 | **Replay RPC riêng của frontend** | Gọi đúng 2 endpoint nội bộ web dùng: `StreamGenerate` (sinh nội dung, body là list positional 69 phần tử) + `batchexecute` (mọi thứ khác) | `client.py`, `constants.py` |
| 5 | **Parse mảng lồng theo index-path** | Response là mảng vô danh lồng nhau; mọi field bới bằng đường index cứng `get_nested_value(data,[12,7,0])` (ảnh ở `[12,7,0]`) | `utils/parsing.py`, `_parse_candidate` |
| 6 | **Bọc thành server tương thích OpenAI** | FastAPI expose `POST /v1/images/generations`, `POST /v1/chat/completions` (SSE), `/images/{file}` static → consumer chỉ đổi `base_url` | `server/main.py`, `server/service.py` |

**Bài học cốt lõi:** điều khiến gemini-webapi **không cần extension** không phải phép thuật — mà là **tầng 1 (`curl_cffi impersonate=chrome`)** đánh lừa được bot-detection, cộng với việc **Gemini chỉ gác cửa bằng cookie + token scrape** (tầng 2). Pure-Python đủ để giả làm browser.

---

## 2. Map từng tầng sang ChatGPT — cái gì bê thẳng, cái gì không

| Tầng | Bê sang ChatGPT? | Chi tiết |
|------|------------------|----------|
| 1. TLS impersonation | ✅ **Bê thẳng** | `curl_cffi impersonate="chrome"` vượt được Cloudflare TLS/`__cf_bm` của chatgpt.com y như với Google. Đây là cùng một kỹ thuật. |
| 2. Session = cookie + token | ✅ **Có analog trực tiếp** | ChatGPT: cookie `__Secure-next-auth.session-token` (httpOnly) → GET `https://chatgpt.com/api/auth/session` đổi lấy **`accessToken` JWT**. Đây đúng là bản sao của bước scrape `SNlM0e`. Cookie dán từ DevTools như 1PSID. |
| 3. Xoay session nền | ✅ **Bê được** | JWT của ChatGPT sống ngắn (~ vài chục phút–vài giờ); làm tươi bằng cách gọi lại `/api/auth/session` định kỳ (cookie session-token sống lâu hơn). Cùng pattern background-refresh như `rotate_1psidts`. |
| 4. Replay RPC | ⚠️ **Bê được nhưng khác hình** | ChatGPT: `POST /backend-api/conversation` (1 lượt hội thoại kích hoạt tool tạo ảnh) trả **SSE stream**, không phải list positional. Phải dựng body conversation-turn + đọc SSE. |
| 5. Parse | ⚠️ **Khác cơ chế** | ChatGPT trả SSE event JSON có cấu trúc (không phải mảng vô danh) — **dễ parse hơn** Gemini. Ảnh về dưới dạng asset `file-...` → cần bước 2: `GET /backend-api/files/{id}/download` ra URL `*.oaiusercontent.com`. |
| 6. Server OpenAI-compatible | ✅ **Bê thẳng** | Copy nguyên `server/` của gemini-webapi: cùng FastAPI, cùng `/v1/images/generations`, cùng static `/images`. **StoryForge điểm `image_api_url` vào đây là xong** (provider `dalle` đã POST đúng shape này). |
| — | ❌ **KHÔNG có sẵn trong pattern Gemini** | **Sentinel proof-of-work + Cloudflare Turnstile.** `POST /backend-api/conversation` đòi header `openai-sentinel-proof-token` (vòng hash SHA3-512 trên ~18 trường browser-config, seed/độ khó lấy từ `GET /backend-api/sentinel/chat-requirements`) + token Turnstile. **Gemini không có lớp này nên gemini-webapi không dạy cách giải.** Đây là 20% còn lại phải tự xử. |

---

## 3. Tầng "đúc token" — chỗ DUY NHẤT phải quyết (vì Gemini không có)

Đây là khác biệt sống còn. Gemini chỉ cần cookie + TLS impersonation. ChatGPT thêm Sentinel PoW + Turnstile trên endpoint conversation. Pure-Python `curl_cffi` **vượt được TLS/Cloudflare nhưng KHÔNG tự đúc được PoW/Turnstile token**. Ba cách xử lý, xếp theo độ nên thử:

### Cách A — Endpoint `codex/responses` (né luôn PoW) ⭐ thử trước
- `POST /backend-api/codex/responses` với `tools:[{type:"image_generation"}]` trả **base64 PNG inline**, và **research trước đó KHÔNG thấy Sentinel/PoW** trên đó (xem `docs/chatgpt-image-flowkit-spec.md` §A).
- Nếu đúng: pattern gemini-webapi bê được **100%** (curl_cffi + cookie/JWT + FastAPI wrapper), **không cần đúc PoW, không cần browser**. Đây là kịch bản đẹp nhất.
- Bẫy: endpoint này auth bằng **OAuth token của `auth.openai.com`** (luồng login khác JWT web thường) — phải verify token này lấy/được làm tươi thế nào.

### Cách B — Reimplement PoW bằng Python
- PoW là hàm **tất định**: lấy seed + difficulty từ `/sentinel/chat-requirements`, chạy vòng hash SHA3-512 tới khi prefix khớp difficulty, nhét vào `openai-sentinel-proof-token`. Có thể viết thuần Python.
- Turnstile khó hơn (bytecode VM obfuscate) — có thể không bắt buộc cho tài khoản Plus đã đăng nhập lâu, cần đo thực tế.
- Nhược: **vỡ mỗi lần OpenAI đổi web-build** (đổi danh sách trường config / thuật toán). Bảo trì cao. Chỉ làm nếu A thất bại.

### Cách C — Browser tí hon chỉ để đúc token (lai)
- Giữ `curl_cffi` làm tầng request chính (nhanh, nhẹ), nhưng dùng **một browser headless (Playwright) hoặc chính extension FlowKit** **chỉ để chạy JS đúc PoW/Turnstile token** trong page-world, rồi đưa token cho client Python gắn vào header.
- Đây là điểm giao với FlowKit hiện có: FlowKit đã có cơ chế "nhờ page-world chạy `grecaptcha.execute()`" (`injected.js`) — y hệt nhu cầu đúc Sentinel token. Tức **FlowKit không bị vứt đi, mà co lại thành "máy đúc token"**, còn toàn bộ logic request + parse + server chuyển sang pattern gemini-webapi sạch.

**Khuyến nghị:** Phase 0 đo Cách A trước (rẻ nhất, né hẳn PoW). A fail → Cách C (tái dùng FlowKit làm token-minter). Cách B là cuối cùng.

---

## 4. Layout module đề xuất: `chatgpt_webapi` (gương theo gemini-webapi)

```
chatgpt_webapi/
  client.py              # ChatGPTClient: init() → /api/auth/session lấy JWT; generate_image()
  constants.py           # Endpoints (conversation, sentinel, files/download, auth/session), Headers
  auth/
    session.py           # đổi cookie session-token → accessToken JWT  (analog get_access_token.py)
    refresh.py           # background làm tươi JWT định kỳ            (analog rotate_1psidts.py)
    sentinel.py          # [chỉ nếu Cách B/C] lấy chat-requirements + đúc proof-token
  transport.py           # curl_cffi AsyncSession(impersonate="chrome")  ← tầng 1, copy y hệt
  parsing.py             # đọc SSE event stream → gom message + file-id  (analog parsing.py)
  files.py               # GET /backend-api/files/{id}/download → tải bytes
  types/image.py         # GeneratedImage.save()                         (copy từ gemini-webapi)
server/                  # COPY NGUYÊN từ gemini-webapi, chỉ đổi service.py trỏ ChatGPTClient
  main.py                # /v1/images/generations, /v1/chat/completions, /images static
  service.py             # GeminiService → ChatGPTService
  schemas.py             # + thêm field reference_images cho character consistency (xem §5)
```

Tầng 1 (`transport.py`), tầng 6 (`server/`), và `types/image.py` **copy gần như nguyên** từ gemini-webapi. Công việc thật nằm ở `auth/` + `parsing.py` (SSE) + tầng đúc token (§3).

---

## 5. Nhất quán nhân vật (ràng buộc lõi của comic) — đừng quên

Server gemini-webapi **chưa** expose ảnh tham chiếu qua `/v1/images/generations` (`schemas.py:83` chỉ có `prompt`). Nhưng đây là **yêu cầu sống còn của comic** (giữ nhân vật giống nhau giữa các panel). Khi copy `server/` sang ChatGPT, phải:
- Thêm field `reference_images: list[str]` vào `ImageGenerationRequest`.
- ChatGPT `conversation`/`codex` đều nhận ảnh input (upload qua `/backend-api/files` → đính `file-id` vào message) → truyền refs xuống. `gpt-image-1` mạnh về giữ nhân vật từ ảnh tham chiếu.
- StoryForge: thêm provider `chatgpt-web` vào switch `image_generator.generate_with_reference` (cạnh `dalle`/`seedream`/`flowkit`), trỏ vào server local này.

---

## 6. Cách StoryForge tiêu thụ (gần như zero đổi cho đường cơ bản)

1. Chạy `chatgpt_webapi/server` như sidecar (vd `http://localhost:8001/v1`).
2. Đường **không ref**: set `image_provider=dalle`, `image_api_url=http://localhost:8001/v1`, `image_api_key=<key>` → provider `_generate_dalle` (đã POST `/v1/images/generations`) chạy thẳng, **không sửa code StoryForge**.
3. Đường **có ref (comic)**: thêm provider `chatgpt-web` gọi endpoint edits mở rộng ở §5.

→ Toàn bộ FlowKit relay + WS + captcha bridge **không còn nằm trên đường đi của ChatGPT** (trừ khi chọn Cách C, lúc đó FlowKit co lại chỉ còn vai trò đúc token).

---

## 7. Phased plan (risk-first)

- **Phase 0 — verify tầng đúc token (sống/chết):**
  - 0a: từ console tab ChatGPT đã login, `fetch('/backend-api/codex/responses', {tools:[image_generation]})` — có trả base64, không 403? (Cách A)
  - 0b: thử `curl_cffi impersonate=chrome` + cookie session-token gọi `/api/auth/session` từ Python — lấy được JWT không?
  - 0c: nếu A fail, đo `/sentinel/chat-requirements` để ước lượng độ khó reimplement PoW (Cách B) hoặc chốt Cách C.
- **Phase 1 — `transport.py` + `auth/session.py`**: dựng client Python lấy JWT, gọi được 1 endpoint đọc (vd list conversations) → xác nhận tầng 1+2 chạy.
- **Phase 2 — `parsing.py` (SSE) + `files.py`**: sinh 1 ảnh thật, tải bytes về đĩa.
- **Phase 3 — copy `server/` + ChatGPTService**: lên endpoint OpenAI-compatible, StoryForge trỏ `dalle` vào.
- **Phase 4 — ref images (§5)** + provider `chatgpt-web` cho comic consistency.

## 8. Rủi ro & fallback
- **Sentinel/PoW vẫn là nút thắt** (Phase 0). Nếu cả A lẫn C đều không ra ảnh → đường free ChatGPT bất khả thi ổn định.
- **Capacity/ban**: Plus ~50 ảnh/3h; comic nhiều panel có thể đốt sạch hạn mức 1 lần chạy; automation account cá nhân có rủi ro khóa. → ChatGPT nên là provider cao cấp/chọn lọc, không phải workhorse.
- **Fallback**: provider `gpt-image-1` trả phí (`api.openai.com/v1/images/generations`) gắn cùng seam `image_generator.generate()` làm sàn tin cậy — bật bằng config flag.

> Caveat: mọi claim protocol ChatGPT nhạy theo thời gian (OpenAI đổi web-build thường xuyên). Re-capture HAR từ session thật trước khi code Phase 1.
