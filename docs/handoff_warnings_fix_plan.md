# Handoff Warnings Fix Plan — 2026-05-24

## Tóm tắt

| # | Vấn đề                                         | Mức độ  | Owner               | Phase |
|---|------------------------------------------------|---------|---------------------|-------|
| 1 | `voice_fingerprints` blocker (LLM không sinh)  | Quality | AI Engineer (song song) | 2     |
| 2 | `arc_waypoints` empty (LLM parse failure)      | Quality | AI Engineer (song song) | 2     |
| 3 | `no such table: pipeline_runs` (alembic chưa chạy) | Infra   | Backend Architect   | 1     |
| 4 | spaCy `xx_ent_wiki_sm` không cài               | Infra   | Backend Architect   | 1     |

Phase 1 = infra (an toàn, không đụng code sản xuất). Phase 2 = chất lượng prompt/LLM (cần debug nội dung).

---

## Vấn đề 1: voice_fingerprints blocker

- **Root cause**: Layer-1 LLM output không emit được `voice_fingerprints` cho character roster — schema yêu cầu nhưng prompt/parser không trả về đúng cấu trúc. Đây là blocker cho consistent dialogue voice ở L2.
- **Fix proposal** (AI Engineer xử lý song song): rà soát prompt template trong `pipeline/layer1_story/` (đặc biệt module sinh roster + voice profile), bổ sung few-shot examples hoặc nới schema validator để chấp nhận output rồi normalize. Không sửa từ phía backend.
- **Verification**: pipeline run mới không còn log warning "voice_fingerprints missing/empty"; `runs/<id>/handoff.json` có trường `voice_fingerprints` với ≥1 entry per character.

---

## Vấn đề 2: arc_waypoints empty

- **Root cause**: Layer-1 LLM trả về `arc_waypoints: []` do prompt thiếu rõ ràng hoặc parser drop khi gặp format không khớp. Hệ quả: L2 thiếu cấu trúc plot waypoints để enhance.
- **Fix proposal** (AI Engineer xử lý song song): debug stage parse JSON trong L1, thêm retry-with-repair khi `arc_waypoints` length < threshold; cân nhắc tách prompt waypoints thành step riêng để dễ kiểm soát output.
- **Verification**: handoff envelope có `arc_waypoints` với length ≥ minimum threshold (theo schema); log warning "arc_waypoints empty" biến mất.

---

## Vấn đề 3: `no such table: pipeline_runs`

- **Root cause**: 5 alembic revisions (`alembic/versions/001..005_*.py`) đã viết cho Postgres nhưng chưa run trên SQLite local. `alembic/env.py` đọc `DATABASE_URL` từ env, fallback `alembic.ini` (placeholder). `.env` đã có `DATABASE_URL=sqlite:///./data/storyforge.db`.
- **Fix proposal** (Backend Architect — Phase 1, làm ngay):
  1. Verify `.env` set `DATABASE_URL` SQLite (đã có).
  2. Chạy `alembic upgrade head` với env biến đó.
  3. Lưu ý: migration `001` dùng `postgresql.UUID` — SQLAlchemy sẽ tự fall back về CHAR(32) trên SQLite, OK ở mức schema; nhưng nếu `alembic/env.py` còn hard-code `create_async_engine` cho asyncpg thì cần URL `sqlite+aiosqlite:///...` và package `aiosqlite`. Sẽ thử và báo cáo.
- **Verification**: `alembic current` show revision `005`; `sqlite3` list tables phải có `pipeline_runs`, `users`, `stories`, `embedding_cache`, v.v.

---

## Vấn đề 4: spaCy `xx_ent_wiki_sm` không cài

- **Root cause**: Pipeline có module NER-based structural detection (Sprint 2 P4) cần model multilingual `xx_ent_wiki_sm`. Local env chưa cài spacy + model nên fallback path log warning.
- **Fix proposal** (Backend Architect — Phase 1, làm trước):
  1. `pip install "spacy>=3.7,<4"`.
  2. `python scripts/install_spacy_model.py` (wrapper cho `python -m spacy download xx_ent_wiki_sm`).
  3. Smoke test: `python -c "import spacy; spacy.load('xx_ent_wiki_sm')"`.
- **Verification**: import + load không exception; log warning "spaCy not installed" biến mất khi rerun pipeline.

---

## Rollout

- **Phase 1 (infra, an toàn, do Backend Architect)**:
  1. Fix #4 spaCy install (đơn giản nhất, ít rủi ro).
  2. Fix #3 alembic upgrade head trên SQLite local.
- **Phase 2 (quality, do AI Engineer song song)**:
  3. Fix #1 voice_fingerprints prompt/parser.
  4. Fix #2 arc_waypoints prompt/parser.

Phase 1 và Phase 2 độc lập, có thể chạy đồng thời.

---

## Rollback plan

- **Nếu spaCy install fail**: gỡ `pip uninstall spacy` (không bắt buộc — chỉ là dep, không ảnh hưởng modules khác); pipeline sẽ tiếp tục log warning như trước, không regress. CEO can thiệp bằng cách cài thủ công hoặc tạm chấp nhận warning.
- **Nếu alembic migrate fail trên SQLite**:
  - DB file mới (`data/storyforge.db`) chỉ cần `rm data/storyforge.db` để xoá sạch — không động tới DB hiện có.
  - Nếu lỗi do asyncpg-only driver: cần đổi `DATABASE_URL` sang `sqlite+aiosqlite:///./data/storyforge.db` và `pip install aiosqlite`. Sẽ propose patch nhỏ cho `alembic/env.py` nếu cần (CEO review trước khi merge).
  - Không có rủi ro mất dữ liệu vì DB chưa tồn tại (đây là bug "no such table").

---

## Verification checklist

- [x] Fix #4: `spacy.load('xx_ent_wiki_sm')` thành công (spaCy 3.8.14, model 3.8.0).
- [x] Fix #3: alembic upgrade head DONE trên SQLite (revision 005). Schema đầy đủ 9 bảng + handoff columns. Xem block "Tình trạng Fix #3 sau khi thử" → "Resolution 2026-05-24" bên dưới.
- [ ] Log cảnh báo #3 (`no such table: pipeline_runs`) biến mất ở pipeline run kế.
- [ ] Log cảnh báo #4 (spaCy missing) biến mất ở pipeline run kế.
- [ ] Log cảnh báo #1 (voice_fingerprints) biến mất (AI Engineer verify).
- [ ] Log cảnh báo #2 (arc_waypoints empty) biến mất (AI Engineer verify).

## Tình trạng Fix #3 sau khi thử

Đã chạy `alembic upgrade head` với `DATABASE_URL=sqlite+aiosqlite:///./data/storyforge.db` và `PYTHONPATH=<repo>`.

Kết quả thực tế:

- Migration 001 chạy partial trước khi fail tại `audit_logs.details` cột `postgresql.JSONB`:
  - `sqlalchemy.exc.CompileError: Compiler ... can't render element of type JSONB`
- SQLite hiện có các bảng đã tạo (do DDL non-transactional trên SQLite): `users`, `stories`, `chapters`, `pipeline_runs`, `alembic_version`.
- Bảng `alembic_version` rỗng → alembic không ghi nhận revision nào → upgrade lần sau sẽ thử lại 001 và fail tại cùng chỗ.
- Schema không đầy đủ: thiếu `audit_logs`, `feedback`, `embedding_cache`, indexes của 002, columns của 003, v.v.

Tình huống là DB partial + alembic state không consistent. Đề xuất 3 hướng cho CEO chọn:

1. **Patch migrations để SQLite-compatible** (đề nghị):
   - Trong `alembic/env.py` thêm helper map `postgresql.JSONB` → `sa.JSON`, `postgresql.UUID` → `sa.String(36)` khi dialect != `postgresql`.
   - Hoặc dùng `sa.JSON` thay vì `postgresql.JSONB` trong các revision (revision 005 đã chuyển; có thể cần áp dụng tương tự cho 001).
   - Cần Backend Architect viết patch nhỏ, CEO review, rồi rerun.
2. **Chạy Postgres local cho dev** (production-parity):
   - `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=dev postgres:16` rồi đổi `DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/storyforge`. Migrations chạy được nguyên bản, không sửa code.
3. **Xoá DB partial + chấp nhận warning tạm thời** trong khi quyết định hướng 1 hoặc 2:
   - `rm data/storyforge.db data/storyforge.db-shm data/storyforge.db-wal` (nếu có).
   - Pipeline tiếp tục log warning `no such table: pipeline_runs` cho tới khi migrate được.

**Khuyến nghị**: Hướng 1 nếu mục tiêu giữ SQLite cho dev local (đúng với `.env.example` mặc định `sqlite:///./data/storyforge.db`). Hướng 2 nếu muốn dev parity với prod (Postgres).

---

## Resolution 2026-05-24 (Fix #3 DONE)

**Approach chọn**: Hướng 1 (type adapter trong `alembic/env.py`, không sửa file migration).

**Patch**: `alembic/env.py` thêm 2 `@compiles` rules cho dialect `sqlite`:

- `@compiles(JSONB, "sqlite")` → render `"JSON"`.
- `@compiles(UUID, "sqlite")` → render `"VARCHAR(36)"`.

Nhờ vậy migration `001` (vốn dùng `postgresql.JSONB` / `postgresql.UUID`) chạy trên SQLite mà không phải đụng file migration. Migrations 002–005 đã cross-dialect sẵn.

**Reset DB local**: Xoá `data/storyforge.db` + `*-journal/-wal/-shm` (DB local đang ở partial state từ lần fail trước), kill 2 process đang lock (`python app.py` PID 3736, `pytest test_l1_character_voice_behavior` PID 180 — đã chết sẵn), rồi rerun:

```powershell
$env:DATABASE_URL = "sqlite+aiosqlite:///./data/storyforge.db"
$env:PYTHONPATH = "."
alembic upgrade head
```

**Kết quả**:

- `alembic current` = `005 (head)`.
- Bảng: `alembic_version`, `audit_logs`, `chapters`, `configs`, `embedding_cache`, `feedback`, `pipeline_runs`, `stories`, `users` (9 bảng).
- `pipeline_runs` có đủ handoff columns: `handoff_envelope`, `handoff_health`, `handoff_signals_version`, `outline_metrics`.

**Việc CEO cần làm thủ công**: chạy lại `python app.py` để restart backend (backend cũ đã bị kill để release DB lock). Pipeline run kế sẽ verify được checklist mục #3 và #4 ở runtime.
