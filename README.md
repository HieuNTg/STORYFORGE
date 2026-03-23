# StoryForge

**Tự động tạo truyện kịch tính và kịch bản video bằng AI.**

Pipeline 3 lớp biến ý tưởng thành truyện hoàn chỉnh, mô phỏng nhân vật để tăng kịch tính, rồi xuất kịch bản video với storyboard chi tiết.

---

## Pipeline

```
Ý tưởng → [Layer 1: Tạo Truyện] → [Layer 2: Mô Phỏng Kịch Tính] → [Layer 3: Kịch Bản Video] → Output
```

### Layer 1 — Tạo Truyện

- Tạo nhân vật với tính cách, tiểu sử, động lực
- Xây dựng bối cảnh thế giới (world-building)
- Tạo dàn ý chi tiết từng chương
- Viết chương tự động với rolling context (theo dõi trạng thái nhân vật, sự kiện cốt truyện)
- Hỗ trợ streaming real-time khi viết

### Layer 2 — Mô Phỏng Tăng Kịch Tính

- Phân tích mối quan hệ và xung đột giữa nhân vật
- Mỗi nhân vật trở thành AI agent tự trị — tương tác, đối đầu, phản bội
- Trích xuất tình huống kịch tính từ mô phỏng
- Viết lại truyện với drama score cao hơn

### Layer 3 — Kịch Bản Video

- Tạo storyboard: shot type, camera movement, mood
- Tạo image prompt cho AI image generation
- Kịch bản lồng tiếng với cảm xúc
- Mô tả hình ảnh nhân vật và bối cảnh

---

## Tính năng

| Tính năng | Mô tả |
|---|---|
| **Character State Tracking** | Theo dõi trạng thái nhân vật qua từng chương (tâm trạng, hành động, quan hệ) |
| **Model Routing** | Dùng cheap model cho tóm tắt/phân tích, model chính cho sáng tác — tiết kiệm ~45% chi phí |
| **Streaming Preview** | Xem trực tiếp AI viết từng chương real-time |
| **File Export** | Xuất TXT, Markdown, JSON — download từng file hoặc ZIP |
| **Quality Metrics** | Chấm điểm tự động 4 chiều: mạch lạc, nhân vật, kịch tính, văn phong (1-5) |
| **Agent Review** | Phòng ban AI đánh giá chất lượng sau mỗi layer |
| **Checkpoint/Resume** | Lưu tiến trình, resume pipeline từ bất kỳ layer nào |
| **LLM Cache** | Cache response LLM, giảm chi phí khi chạy lại |
| **OpenClaw** | Hỗ trợ backend local với auto-fallback sang API |

---

## Cài đặt

### Yêu cầu

- Python 3.10+
- API key từ provider tương thích OpenAI (OpenAI, DeepSeek, Gemini, Groq, OpenRouter, Ollama, v.v.)

### Cài đặt

```bash
git clone https://github.com/HieuNTg/novel-auto.git
cd novel-auto
pip install -r requirements.txt
```

### Chạy

```bash
python app.py
```

Mở trình duyệt tại `http://localhost:7860`

---

## Cấu hình

Vào tab **Cài Đặt** trong giao diện web:

| Cấu hình | Mô tả | Mặc định |
|---|---|---|
| API Key | Key từ LLM provider | — |
| Base URL | Endpoint API | `https://api.openai.com/v1` |
| Model | Model chính (sáng tác) | `gpt-4o-mini` |
| Cheap Model | Model rẻ (tóm tắt, phân tích) | _(trống = dùng model chính)_ |
| Temperature | Độ sáng tạo | `0.8` |
| Backend | `api` hoặc `openclaw` | `api` |

Cấu hình lưu tại `data/config.json`.

---

## Cấu trúc dự án

```
storyforge/
├── app.py                          # Gradio UI
├── config.py                       # Quản lý cấu hình
├── models/
│   └── schemas.py                  # Pydantic models
├── services/
│   ├── llm_client.py               # Client giao tiếp LLM API
│   ├── llm_cache.py                # Cache LLM responses
│   ├── quality_scorer.py           # Chấm điểm chất lượng truyện
│   ├── prompts.py                  # Prompt templates
│   └── openclaw_manager.py         # Quản lý OpenClaw backend
├── pipeline/
│   ├── orchestrator.py             # Điều phối pipeline 3 lớp
│   ├── layer1_story/
│   │   └── generator.py            # Tạo truyện từ đầu
│   ├── layer2_enhance/
│   │   ├── analyzer.py             # Phân tích quan hệ nhân vật
│   │   ├── simulator.py            # Mô phỏng AI agent
│   │   └── enhancer.py             # Viết lại tăng kịch tính
│   ├── layer3_video/
│   │   └── storyboard.py           # Tạo storyboard & kịch bản
│   └── agents/                     # Phòng ban AI đánh giá
│       ├── agent_registry.py
│       ├── drama_critic.py
│       ├── continuity_checker.py
│       ├── character_specialist.py
│       ├── dialogue_expert.py
│       └── editor_in_chief.py
├── requirements.txt
└── docs/                           # Tài liệu kỹ thuật
```

---

## Sử dụng

1. **Cài đặt API** — Vào tab Cài Đặt, nhập API key và chọn model
2. **Nhập ý tưởng** — Chọn thể loại, phong cách, mô tả ý tưởng truyện
3. **Điều chỉnh** — Số chương, số nhân vật, số từ/chương, mức kịch tính
4. **Chạy Pipeline** — Nhấn nút, theo dõi tiến trình real-time
5. **Xem kết quả** — Các tab: Truyện Gốc, Mô Phỏng, Truyện Kịch Tính, Kịch Bản Video, Chất Lượng
6. **Xuất file** — Download TXT/Markdown/JSON hoặc ZIP toàn bộ

---

## API tương thích

Hỗ trợ mọi API tương thích OpenAI:

- OpenAI (GPT-4o, GPT-4o-mini)
- DeepSeek
- Google Gemini (qua OpenAI-compatible endpoint)
- Groq
- Together AI
- OpenRouter
- Ollama (local)
- Bất kỳ provider nào có endpoint `/v1/chat/completions`

---

## License

MIT
