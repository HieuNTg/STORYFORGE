# STORYFORGE - BÁO CÁO TỔNG HỢP TIẾN ĐỘ & HƯỚNG DẪN TIẾP TỤC

- **Ngày lập:** 2026-11-13
- **Nguồn context:** Session Claude Code `task-15-dead-code-review` (ID: `bbfbaa0d-acb7-4e26-bef8-c626f00e9cda`)
- **Trạng thái repo:** Nhánh `deps/security-upgrade` (ahead 3 commits so với `master`, working tree clean)

---

## 1. Bối cảnh & Toàn cảnh công việc đã diễn ra

Phiên làm việc `task-15-dead-code-review` bắt đầu từ yêu cầu đánh giá toàn diện STORYFORGE (`STORYFORGE-review.md`) và sau đó thực hiện chuyển đổi dự án thành **bản Open-Source hoàn chỉnh (v2.0.0)** dành cho người dùng tự host (self-hosted) với tiêu chí:
1. Chạy mặc định qua **Docker (`docker compose up`)**.
2. **Local-first, an toàn tuyệt đối trên localhost:** bind `127.0.0.1`, chặn DNS rebinding/Host header injection, CSRF double-submit, chặn lộ secret qua FlowKit WebSocket.
3. Chỉ dùng **SQLite**, bỏ PostgreSQL / Redis ngoài luồng, không cần migration dữ liệu cũ.
4. Loại bỏ các provider dùng web-session không chính thống (Gemini Web, Codex image, FlowKit, qwen-local).
5. Dọn dẹp code rác, code chết, tài liệu lỗi thời, module không còn sử dụng.

---

## 2. Những hạng mục ĐÃ HOÀN THÀNH & ĐÃ PUSH LÊN MASTER

Toàn bộ kế hoạch 23 Tasks (gồm Phase 1 & Phase 2 theo `docs/superpowers/plans/2026-11-11-local-open-source-release.md`) đã được triển khai hoàn tất trên nhánh `release/local-open-source`, kiểm thử toàn diện và **đã merge vào `master` (commit `4b4d184`) rồi push lên `origin/master`**.

### Chi tiết Task 15 (`task-15-dead-code-review`):
- **Commit:** `358ff11` - `refactor: drop discarded per-chapter L1 reviews, debug probes and dead modules`
- **Kết quả:**
  - Ngừng truyền `chapter_complete_callback` từ `run_full_pipeline`: loại bỏ việc gọi `AgentRegistry.run_review_cycle` sau từng chương (kết quả trước đây bị vứt bỏ, gây tốn token LLM vô ích). Review tổng thể sau L1 vẫn được giữ nguyên.
  - Xóa toàn bộ các debug probe log thừa thãi: `PROBE-O1..O6`, `PROBE-G1..G2`.
  - Chuyển utilities chấm điểm từ `tests/benchmarks` sang `services/pipeline/scoring_calibration.py` (giữ shim tương thích ngược).
  - **Xóa bỏ các module chết và test đi kèm:**
    - `services/emotion_classifier.py`
    - `services/genre_library.py`
    - `services/story_brancher.py`
    - `services/structured_output.py`
    - `services/web_reader_generator.py`
    - `services/onboarding.py`
    - `services/audit_logger.py` & `services/_audit_store.py`
    - `services/_rate_limiter_base.py` & `services/_rate_limiter_inmemory.py`
    - `pipeline/layer2_enhance/structural_detector.py`
    - `models/schemas.py:UserProfile`
    - Hàm thừa `persist_chapter_semantic_findings` trong `orchestrator_layers.py`.
  - Giảm hơn 4.400 dòng code thừa và test không cần thiết.

### Các task còn lại trong bản release 2.0.0:
- **Bảo mật & mạng:** Bind `127.0.0.1`, chặn traversal path ở FlowKit style reference, cấu hình Origin/Host header validation.
- **Frontend & UI:** Khắc phục treo stream Forge (`forge.ts`), gỡ bỏ NUL byte / mojibake, làm sạch lint lỗi Next/React, chuyển `shadcn` sang devDependencies.
- **Docker & CI:** Tạo `docker/api.Dockerfile`, `docker/web.Dockerfile`, `compose.yaml`, `compose.release.yaml`, thêm GitHub Actions CI (`.github/workflows/ci.yml`), Dependabot và Release workflow.
- **Tài liệu:** Viết lại toàn bộ `README.md`, `README.vi.md`, `docs/self-hosting.md`, `SECURITY.md`, `CHANGELOG.md` chuẩn hóa theo phiên bản 2.0.0.
- **Bộ test:** Đã chạy qua 5.092 test pytest, 145 vitest và build frontend không lỗi.

---

## 3. Công việc trên nhánh hiện tại: `deps/security-upgrade`

Sau khi `master` được push lên GitHub, hệ thống CI và Dependabot phát hiện 17 cảnh báo bảo mật phụ thuộc Python (từ `pip-audit`). Nhánh `deps/security-upgrade` được tạo để giải quyết.

### 3 commit đã thực hiện trên nhánh:
1. `c984f60` - `build(deps): patch vulnerable Python dependencies`:
   - Nâng cấp 16 package phụ thuộc có lỗ hổng bảo mật: `torch` (2.15 CPU), `cryptography`, `sentence-transformers`, `transformers`, `urllib3`, `Pillow`, `setuptools`, `anyio`, v.v.
   - Thêm `starlette >= 1.3.1` trực tiếp.
   - Cập nhật và khóa chặt lại `requirements.lock.txt`.
2. `1140ba7` - `test: run RAG and embeddings on the real chromadb / sentence-transformers stack`:
   - Bổ sung test tích hợp chạy stack ChromaDB và model sentence-transformers thực tế (`tests/test_rag_chromadb_integration.py` và `tests/test_embedding_service_real_model.py`).
3. `72d6be8` - `docs(changelog): record the dependency security upgrade`:
   - Ghi lại nhật ký nâng cấp phụ thuộc trong `CHANGELOG.md`.

---

## 4. Nhiệm vụ ĐANG DỞ DANG: Thay thế ChromaDB bằng SQLite + NumPy Store

### Vấn đề tồn tại với ChromaDB:
- `chromadb 0.4.x` dính CVE (CVE-2026-45830, CVE-2026-45833). Phiên bản 1.x mới hơn lại phát sinh thêm CVE server khác và làm breaking API.
- `chromadb` kéo theo cây phụ thuộc cực kỳ cồng kềnh (`onnxruntime`, `grpcio`, `kubernetes`, `pydantic v1 shim`, v.v.), làm phình to Docker image thêm vài trăm MB.
- Bắt buộc phải ghim `numpy < 2`, gây xung đột với các thư viện tính toán khoa học hiện đại.
- Thực tế trong STORYFORGE: RAG chỉ dùng ở chế độ local nhúng (`PersistentClient`) để lưu ngữ cảnh thế giới/nhân vật cho từng bộ truyện (vài trăm đến vài nghìn đoạn text).

### Thiết kế đã được duyệt (Anh Hiếu đã "ok"):
Thay thế hoàn toàn `chromadb` bằng một vector store thuần **SQLite + NumPy**:

1. **Module `services/vector_store.py` (Lớp `SQLiteVectorStore`):**
   - Lưu trữ dữ liệu vào một file SQLite duy nhất tại `data/rag/rag_store.db` (hỗ trợ cấu hình qua env `RAG_PERSIST_DIR` hoặc fallback về `CHROMA_PERSIST_DIR`).
   - Cấu trúc bảng `embeddings`:
     - `id TEXT PRIMARY KEY`
     - `collection TEXT`
     - `document TEXT`
     - `metadata TEXT` (JSON string)
     - `embedding BLOB` (lưu vector `float32` dưới dạng raw bytes qua `numpy.ndarray.tobytes()`)
     - `created_at REAL`
   - Tìm kiếm vector:
     - Đọc các vector thỏa mãn điều kiện lọc metadata (`where`) ra NumPy array 2D.
     - Tính Cosine Similarity / Dot Product bằng `numpy.dot` (các vector đã được L2-normalize khi index).
     - Lấy Top-K khoảng cách gần nhất.
2. **Cập nhật `services/rag_knowledge_base.py`:**
   - Giữ nguyên 100% public interface: `add_documents()`, `query()`, `query_structured()`, `index_chapter()`, `count()`, `clear()`, `backup()`, `restore()`.
   - Sử dụng `sentence-transformers` với đúng model hiện tại (`keep model embedding consistent`).
   - Tự động bỏ qua index cũ ở `data/chromadb` và ghi log hướng dẫn (dữ liệu sẽ tự động tái lập khi viết chương mới).
3. **Cập nhật dependencies & lockfile:**
   - Xóa `chromadb` khỏi `requirements.txt`.
   - Bỏ giới hạn `numpy<2` (cho phép `numpy>=1.26.0`).
   - Tạo lại `requirements.lock.txt`.
4. **Kiểm thử:**
   - Chuyển `tests/test_rag_chromadb_integration.py` thành `tests/test_rag_sqlite_integration.py`.
   - Chạy kiểm thử pytest để đảm bảo `query_structured` (bộ lọc `where`, `exclude_chapter`, khoảng cách distance) hoạt động chính xác.
   - Chạy `pip-audit` để đảm bảo 0 lỗ hổng bảo mật.

---

## 5. Hướng dẫn các bước cho Developer làm tiếp

Khi mở lại dự án để hoàn thiện nốt nhánh `deps/security-upgrade`, thực hiện theo quy trình sau:

### Bước 1: Kiểm tra trạng thái git
```bash
cd STORYFORGE
git status
# Đảm bảo đang ở nhánh deps/security-upgrade
```

### Bước 2: Hiện thực `services/vector_store.py`
Tạo file `services/vector_store.py` cài đặt `SQLiteVectorStore` như thiết kế ở Mục 4.

### Bước 3: Cập nhật `services/rag_knowledge_base.py`
Thay thế phần khởi tạo `chromadb.PersistentClient` bằng `SQLiteVectorStore`. Đảm bảo các hàm `query_structured` trả về đúng định dạng dict:
```python
{
    "ids": [...],
    "documents": [...],
    "metadatas": [...],
    "distances": [...]
}
```

### Bước 4: Cập nhật `requirements.txt` & lock file
Gỡ `chromadb` ra khỏi `requirements.txt`, cập nhật `numpy>=1.26.0,<3` và chạy:
```bash
python -m uv pip compile pyproject.toml requirements.txt -o requirements.lock.txt
```

### Bước 5: Cập nhật & chạy test suite
```bash
# Đổi tên test hoặc cập nhật test RAG
pytest tests/test_rag_*.py tests/test_embedding_service_real_model.py -v
# Chạy toàn bộ test
pytest -m "not calibration and not bench and not perf"
```

### Bước 6: Kiểm tra bảo mật & commit
```bash
pip-audit -r requirements.lock.txt
git add .
git commit -m "feat(rag): replace chromadb with lightweight sqlite+numpy vector store"
git push origin deps/security-upgrade
```
Sau đó tạo PR để merge nhánh `deps/security-upgrade` vào `master`.
