<h1 align="center">StoryForge</h1>

<p align="center">
  <strong>Nền tảng tạo truyện bằng AI với mô phỏng kịch tính đa tác nhân</strong>
</p>

<p align="center">
  <a href="https://railway.app/new/template?template=https://github.com/HieuNTg/STORYFORGE">
    <img src="https://railway.app/button.svg" alt="Deploy on Railway" height="32" />
  </a>
  &nbsp;
  <a href="https://render.com/deploy?repo=https://github.com/HieuNTg/STORYFORGE">
    <img src="https://render.com/images/deploy-to-render-button.svg" alt="Deploy to Render" height="32" />
  </a>
</p>

<p align="center">
  <a href="README.md">English</a> &nbsp;|&nbsp; <strong>Tiếng Việt</strong>
</p>

<p align="center">
  Biến một ý tưởng một câu thành câu chuyện hoàn chỉnh, giàu kịch tính với hình ảnh nhất quán nhân vật và phông cảnh điện ảnh.<br />
  Tự host. Bảo mật riêng tư. Hoạt động với mọi LLM tương thích OpenAI.
</p>

---

## Tại sao chọn StoryForge?

Hầu hết công cụ viết AI tạo ra những câu chuyện phẳng, dễ đoán. StoryForge tiếp cận khác hơn: các nhân vật trở thành **tác nhân AI tự trị** — tranh luận, liên minh và phản bội nhau trong vòng mô phỏng kịch tính đa chiều. Mô phỏng phát lộ những xung đột mà tác giả chưa từng lên kế hoạch, rồi tự động viết lại câu chuyện xung quanh chúng cho đến khi đạt ngưỡng chất lượng.

---

## Tính năng chính

- **Pipeline 2 lớp** — Tạo truyện → Mô phỏng kịch tính, có checkpoint & tiếp tục, streaming SSE thời gian thực
- **13 tác nhân AI chuyên biệt** — nhân vật tự trị + nhà phê bình kịch tính, tổng biên tập, phân tích nhịp điệu, kiểm tra phong cách, chuyên gia hội thoại...
- **Chấm điểm & tự sửa** — đánh giá LLM theo 4 chiều (mạch lạc, nhân vật, kịch tính, văn phong) với vòng lặp tự động nâng chất
- **Tạo hình ảnh** — chân dung nhân vật nhất quán (IP-Adapter) và phông cảnh điện ảnh, tạo sau mô phỏng kịch tính
- **Hỗ trợ đa nhà cung cấp LLM** — OpenAI, Google Gemini, Anthropic, OpenRouter (290+ model), Ollama (local), hoặc endpoint tùy chỉnh
- **Tiếng Việt & Tiếng Anh** — tạo truyện song ngữ ngay từ đầu
- **Xuất phong phú** — PDF, EPUB, HTML web reader, ZIP với các chương và gợi ý hình ảnh
- **Chế độ đọc nhánh tương tác** — chọn-hướng-phiêu-lưu với các nhánh sinh bởi LLM
- **Giao diện Sáng / Tối** — chuyển đổi theme mượt mà với đồng bộ color-scheme toàn bộ trang
- **Tự host, bảo mật** — truyện và API key không bao giờ rời khỏi hạ tầng của bạn
- **Cache sẵn sàng production** — cache LLM bằng Redis cho triển khai đa worker, tự động fallback SQLite cho phát triển
- **Định tuyến model thông minh** — model rẻ cho phân tích, model cao cấp cho viết (~45% tiết kiệm chi phí)

---

## Cài đặt nhanh

### Docker (khuyến nghị)

```bash
docker compose up
```

Mở [http://localhost:7860](http://localhost:7860). Xong.

### Cài đặt thủ công

```bash
git clone https://github.com/HieuNTg/STORYFORGE.git
cd STORYFORGE
pip install -r requirements.txt
npm install && npm run build   # biên dịch TypeScript → JS
npm run build:css              # biên dịch Tailwind CSS
python app.py
# → http://localhost:7860
```

### Lần chạy đầu tiên

1. **Cài đặt** → chọn nhà cung cấp AI, nhập API key, chọn model
2. **Tạo truyện** → chọn thể loại, phong cách, mô tả ý tưởng một câu
3. **Chạy Pipeline** → xem quá trình tạo, mô phỏng và tạo hình ảnh stream thời gian thực
4. **Đọc** → đọc truyện hoàn chỉnh hoặc khởi động Chế độ Nhánh tương tác
5. **Xuất** → tải xuống PDF, EPUB, HTML, hoặc ZIP storyboard

---

## Cấu hình

Mọi cài đặt được quản lý qua tab **Cài đặt** trong giao diện web và lưu vào `data/config.json`. Biến môi trường chính cho triển khai Docker:

| Biến | Mô tả | Mặc định |
|:-----|:------|:---------|
| `LLM_PROVIDER` | `openai` \| `gemini` \| `anthropic` \| `openrouter` \| `ollama` | `openai` |
| `LLM_API_KEY` | API key của nhà cung cấp | _(không có)_ |
| `LLM_MODEL` | Model chính để viết (vd. `gpt-4o`) | `gpt-4o` |
| `LLM_BASE_URL` | URL endpoint tùy chỉnh (tương thích OpenAI) | _(mặc định nhà cung cấp)_ |
| `SECRET_KEY` | Bí mật session cho JWT auth | _(tự tạo)_ |
| `REDIS_URL` | Kết nối Redis cho cache production | _(fallback SQLite)_ |
| `PORT` | Cổng server | `7860` |

**Ghi đè model theo lớp** và model ngân sách thứ hai cho phân tích có thể cấu hình trong UI tại Cài đặt → Nâng cao.

---

## Chạy ứng dụng

### Docker Compose (đầy đủ)

```bash
# Khởi động
docker compose up -d

# Xem log
docker compose logs -f

# Dừng
docker compose down
```

### Triển khai một lệnh

```bash
# Railway
railway up

# Render — kết nối repo GitHub và triển khai tự động
```

---

## Cấu trúc dự án

```
storyforge/
├── app.py                      # Điểm vào FastAPI
├── config.py                   # Singleton cấu hình
├── pipeline/                   # Engine tạo 2 lớp
│   ├── orchestrator.py         #   Orchestrator với checkpoint
│   ├── layer1_story/           #   Tạo truyện (nhân vật, thế giới, chương)
│   ├── layer2_enhance/         #   Mô phỏng kịch tính & nâng chất
│   └── agents/                 #   13 tác nhân AI chuyên biệt
├── services/                   # Logic nghiệp vụ tái sử dụng
│   ├── llm/                    #   LLM client với chuỗi dự phòng
│   ├── llm_cache.py            #   Cache hai backend (Redis / SQLite)
│   ├── quality_scorer.py       #   Chấm điểm 4 chiều
│   └── ...                     #   Xuất, xác thực, phân tích, tạo hình ảnh...
├── api/                        # REST endpoint FastAPI
├── web/                        # Frontend Alpine.js + TypeScript (SPA)
├── middleware/                 # Auth, giới hạn tốc độ, audit log
├── models/schemas.py           # Mô hình dữ liệu Pydantic
└── tests/                      # Bộ kiểm tra
```

---

## Đóng góp

Đóng góp luôn được chào đón! Vui lòng đọc [CONTRIBUTING.md](CONTRIBUTING.md) để bắt đầu — bao gồm cài đặt môi trường phát triển, quy chuẩn code, quy trình PR và cách tìm vấn đề phù hợp cho người mới.

---

## Giấy phép

[MIT](LICENSE) — Bản quyền 2026 StoryForge Contributors
