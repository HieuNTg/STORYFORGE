# StoryForge: bản phát hành mã nguồn mở chạy local (giai đoạn 1–2)

- Ngày: 2026-11-11
- Nhánh: `release/local-open-source`
- Nguồn vấn đề: `../STORYFORGE-review.md`, bản đánh giá toàn diện ngày 2026-11-11, nằm ngoài repo.

## 1. Mục đích

Chủ dự án muốn STORYFORGE trở thành **dự án mã nguồn mở mà ai cũng clone về chạy được trên máy cá nhân**. Mỗi người dùng một mình và mang API key LLM của chính họ. Cách chạy chính là **Docker**.

Người đọc của bản phát hành này:
- **Người dùng:** người viết truyện, biết chạy `docker compose up`, không cần biết Python hay Node.
- **Người đóng góp:** lập trình viên clone repo về sửa code, cần CI, tài liệu đúng và chạy dev được trên mọi hệ điều hành.

Thành công nghĩa là:
1. Một người lạ chỉ cần `git clone` rồi `docker compose up` là mở được `http://localhost:3001`, nhập API key và sinh được truyện. Không phải sửa file nào.
2. Không ai ngoài máy đó, kể cả một trang web lạ đang mở trên trình duyệt, đọc được key hay truyện của người dùng.
3. Mỗi PR được CI chạy test trên Linux.
4. Tài liệu nói đúng những gì code làm.

## 2. Mục tiêu, phi mục tiêu, phản mục tiêu

**Mục tiêu (giai đoạn 1–2):**
- Vá các lỗ hổng bảo mật trong mô hình local.
- Sửa các bug đúng mà bản đánh giá đã xác minh.
- Chạy được bằng Docker chỉ với một lệnh.
- Gỡ các provider dùng phiên đăng nhập web.
- Có CI.
- Viết lại tài liệu và dọn repo.

**Phi mục tiêu (để giai đoạn sau, brainstorm riêng):**
- Giai đoạn 3:
  - Lưu thư viện truyện phía server thay cho localStorage.
  - Phát sự kiện tiến độ có kiểu thay cho việc dò log bằng regex.
  - Rà soát và thiết kế lại UI/UX bằng ui-ux-pro-max.
- Giai đoạn 4:
  - Refactor backend: tách `run_full_pipeline` và `process_chapter_post_write`.
  - Gộp 4 chế độ batch, 5 module consistency và các lớp judge.
  - Chọn một mô hình đồng thời.
  - Truyền `run_id` tường minh cho ví chi phí. Bug này có thể sửa sớm ở giai đoạn 1 vì nhỏ (xem 4.2).
- Đóng gói desktop (Tauri/Electron).
- Chế độ nhiều người dùng.

**Phản mục tiêu (làm những điều này là thất bại, dù code vẫn chạy):**
- Người dùng phải tự tạo secret, tự sửa `.env` hoặc tự cài Redis/Postgres mới chạy được.
- API lộ ra ngoài `127.0.0.1` theo mặc định.
- Thay đổi hành vi sinh truyện (prompt, chất lượng, luồng L1/L2) trong hai giai đoạn này. Hai giai đoạn này chỉ đụng tới hạ tầng, bảo mật, độ đúng và tài liệu.
- Xóa test hành vi để CI xanh. Chỉ được xóa hoặc viết lại các test "coverage filler" theo mục 4.5.
- Viết lại lịch sử git (force-push) mà chủ dự án chưa đồng ý.

## 3. Các cách đã cân nhắc

| Cách | Mô tả | Đánh đổi | Quyết định |
|---|---|---|---|
| **A. Local-first, một người dùng, chạy bằng Docker** | Bind localhost, kiểm Host/Origin, gỡ đăng ký nhiều người dùng và RBAC, chỉ giữ một token tùy chọn | Bỏ kịch bản nhiều người dùng chung server | **Chủ dự án chọn** (chọn A, chạy bằng Docker) |
| B. Hoàn thiện chế độ nhiều người dùng | Màn hình login, quyền sở hữu truyện, đóng đăng ký | Thêm 2–3 tuần cho thứ người dùng không cần, diện tấn công lớn hơn | Loại |
| C. Ứng dụng desktop | Bundle mọi thứ thành bộ cài | Bộ cài nặng vài GB, khó bảo trì | Để sau |

Về các provider dùng phiên web (FlowKit/Google Labs, qwen-local/chat.qwen.ai): chủ dự án chọn **gỡ hẳn**, không tách ra plugin. Claude đề xuất gỡ luôn `codex_image_client`, provider gọi endpoint nội bộ ChatGPT bằng OAuth của Codex CLI, vì cùng loại rủi ro. Chủ dự án duyệt khi duyệt tài liệu này.

## 4. Thiết kế

### 4.1 Mô hình bảo mật local

- **Bind:**
  - `app.py` đọc `STORYFORGE_HOST` (mặc định `127.0.0.1`) và `STORYFORGE_PORT` (mặc định `7860`).
  - Trong Docker, container `api` bind `0.0.0.0`, nhưng compose chỉ publish cổng ra `127.0.0.1` của máy chủ.
- **Host/Origin:**
  - Thêm `TrustedHostMiddleware`. Mặc định cho phép `localhost`, `127.0.0.1`, `[::1]` và `api` (tên service trong compose). Mở rộng bằng `STORYFORGE_ALLOWED_HOSTS`.
  - Mọi WebSocket (`branch_websocket`, cùng `flowkit` trước khi bị gỡ) phải kiểm `Origin` theo danh sách CORS.
- **Token truy cập tùy chọn:**
  - Nếu đặt `STORYFORGE_ACCESS_TOKEN`, mọi route `/api/*` và `/media/*` (trừ `/api/health`) yêu cầu header `Authorization: Bearer <token>` hoặc cookie phiên do `/api/session` cấp sau khi nhập token.
  - Frontend có một màn hình nhập token đơn giản, chỉ hiện khi API trả 401.
  - Khi `STORYFORGE_HOST` không phải loopback mà token chưa đặt, app **từ chối khởi động** và báo lỗi rõ ràng.
- **Gỡ chế độ nhiều người dùng:**
  - Gỡ `auth_routes` (register/login), JWT/RBAC (`middleware/rbac.py`, `_rbac_model.py`, `auth_middleware.py`, `services/auth/*`), `account_routes.py` (vốn không được mount), cùng `user_store`/`users.db`.
  - Các dependency `require_permission` trong 45 file được thay bằng một dependency `require_access` duy nhất, kiểm token nếu có cấu hình.
  - Bảng user trong Alembic: tạo migration mới bỏ các bảng auth, không sửa migration cũ.
- **Đổi `base_url` thì phải nhập lại key:** khi `PUT /api/config` đổi host của `llm.base_url` (hoặc của một provider profile) mà request không gửi kèm key mới, key cũ của profile đó bị xóa và API trả về thông báo yêu cầu nhập lại.
- **Secret key tự sinh:**
  - Nếu `STORYFORGE_SECRET_KEY` trống, lần đầu khởi động sẽ sinh một khóa Fernet, ghi vào `data/.secret_key` (quyền 0600) rồi dùng lại các lần sau.
  - Giá trị placeholder như `change-me-in-production` vẫn bị từ chối.
- **Các mục khác:**
  - `/docs` và `/openapi.json` chỉ bật khi `STORYFORGE_DEBUG=1`.
  - CSP bỏ `unsafe-eval`, vốn còn sót từ thời dùng Alpine. Giữ `unsafe-inline` cho script theme nếu cần, hoặc chuyển sang nonce (để builder quyết).
  - Giới hạn kích thước body phải áp dụng cả với request không có `Content-Length` (chunked).
  - Đăng nhập không còn, nên bỏ phần rate limit riêng cho login. Rate limit chung giữ nguyên.

### 4.2 Sửa các bug đúng

1. **`mcp_server.py`:**
   - Dùng `asyncio.run(orch.run_full_pipeline(...))` trong thread worker.
   - Truyền `language` theo từng job, không sửa config global.
   - Thêm test chạy job với fake LLM và kiểm `status == "completed"`.
2. **Ví chi phí:**
   - Truyền `run_id` tường minh vào `charge_wallet` tại `client.py:1611` và `generation.py:457`.
   - Mọi `loop.run_in_executor` đang chuyển công việc có gọi LLM sang thread khác phải đổi sang `asyncio.to_thread` hoặc `contextvars.copy_context().run`.
   - `reset_wallet` không còn ghi đè run toàn cục. `_wallet_state` được dọn khi run kết thúc.
   - Thêm test cho 2 run chạy song song.
3. **`frontend/lib/api/forge.ts`:**
   - Thêm `onclose`: nếu stream đóng mà chưa `settled` thì reject.
   - `onerror` luôn `throw` để không tự retry POST.
   - Thêm test.
4. **Middleware:**
   - Sắp xếp lại để thứ tự chạy thật là TraceID → CORS → BodySize → Security headers → CSRF → RateLimit → Sanitization → Audit → Metrics. Response 413/429 vì thế có header CORS, và log audit có trace ID.
   - Sửa comment trong `app.py`.
   - Thêm test kiểm 413 có header CORS.
5. **Config:**
   - `PUT /config` không còn sửa object đang được pipeline dùng. Mỗi run nhận một bản snapshot (`model_copy(deep=True)`) lúc bắt đầu.
   - Sửa race "initialized trước khi load" trong `config.py`.
6. **Review L1 bị bỏ phí:** bỏ lời gọi `run_review_cycle` sau mỗi chương ở L1 (`orchestrator_layers.py:620-628`), vì kết quả không được dùng. Nếu builder thấy kết quả thực ra có được dùng gián tiếp thì giữ lại và ghi lý do.
7. **Gỡ code chết và debug:**
   - Bỏ 8 dòng log `[PROBE-…]`.
   - Bỏ import `tests.benchmarks` khỏi code production.
   - Bỏ các module chỉ test dùng tới (danh sách ở bản đánh giá, mục 4), kèm test tương ứng.

### 4.3 Phụ thuộc và môi trường

- **Python:**
  - Pin `numpy<2`, vì chromadb 0.4 cần nó.
  - Thêm `aiosqlite` vào requirements runtime.
  - Đặt cận trên hợp lý cho `fastapi`, chọn phiên bản đã chạy test pass.
  - Nâng `python-multipart>=0.0.18`.
  - Bỏ cận `cryptography<44` nếu test vẫn pass.
  - Chuyển `pytest-asyncio` sang `requirements-test.txt`.
  - Bỏ `--extra-index-url` khỏi `requirements.txt`. Torch CPU chỉ cài trong Dockerfile bằng `--index-url` riêng cho đúng gói `torch`.
  - Thêm `requires-python = ">=3.11"` (code dùng `tomllib`).
- **Lockfile:**
  - Tạo lại `requirements.lock.txt` bằng `uv pip compile` cho Linux/py3.12. Dockerfile cài từ lockfile.
  - CI kiểm lockfile khớp với `requirements.txt`.
- **Frontend:**
  - Chuyển `shadcn` sang `devDependencies`.
  - Nâng `next` lên bản vá mới nhất cùng major 16.
  - Mục tiêu: `npm audit --omit=dev` không còn lỗi critical hay high, hoặc ghi rõ lý do cho từng lỗi còn lại.
- **ESLint:** sửa hết 36 error. Script `.cjs` của lighthouse được ignore hoặc chuyển sang ESM. Các lỗi `set-state-in-effect` phải sửa thật.

### 4.4 Docker

Thêm `compose.yaml` ở thư mục gốc; đây là file người dùng chạy. Gỡ `docker-compose.production.yml` (Postgres/Redis). Xem thêm mục 7 về SQLite-only, build và pull image, và Ollama.

```yaml
services:
  api:
    image: storyforge-api
    build: { context: ., dockerfile: docker/api.Dockerfile }
    environment:
      STORYFORGE_HOST: 0.0.0.0
      STORYFORGE_IN_CONTAINER: "1"
    extra_hosts: ["host.docker.internal:host-gateway"]
    volumes: [storyforge-data:/app/data, storyforge-output:/app/output]
    ports: ["127.0.0.1:7860:7860"]
    healthcheck: { test: ["CMD", "python", "-c", "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:7860/api/health')"] }
  web:
    image: storyforge-web
    build: { context: frontend, dockerfile: ../docker/web.Dockerfile }
    environment: { API_ORIGIN: http://api:7860 }
    depends_on: { api: { condition: service_healthy } }
    ports: ["127.0.0.1:3001:3000"]
volumes: { storyforge-data: {}, storyforge-output: {} }
```

- **`docker/api.Dockerfile`:**
  - Build multi-stage. Stage build có `build-essential` và cài wheel từ lockfile. Stage runtime là `python:3.12-slim`, không có compiler.
  - Torch CPU cài riêng bằng `--index-url https://download.pytorch.org/whl/cpu`.
  - Model spaCy `xx_ent_wiki_sm` được tải sẵn lúc build.
  - Chạy bằng `USER storyforge` (uid 10001).
  - `storyforge.log` ghi vào `/app/data/logs`.
- **`docker/web.Dockerfile`:** Next `output: "standalone"`, user không phải root, `node server.js`.
- **`.dockerignore`:** thêm `.env*` (trừ `.env.example`), `tests/`, `docs/`, `*.md` (trừ README), `frontend/node_modules`, `frontend/.next`. Context của `web` là `frontend/`.
- **`next.config.ts`:**
  - Bỏ nhánh static export.
  - `rewrites()` luôn chạy, proxy `/api/*` và `/media/*` tới `API_ORIGIN`. Giá trị này được nhúng lúc build: mặc định `http://api:7860` trong Docker, `http://localhost:7860` khi chạy dev.
  - `compress: false` cả ở production để không buffer SSE.
  - `proxyTimeout` 10 phút ở mọi môi trường.
  - Builder phải xác minh SSE stream được qua proxy của `next start`. Nếu không, fallback là thêm route handler `app/api/[...path]/route.ts` stream thẳng (builder chọn và ghi lại).
- **Dữ liệu:**
  - Volume `storyforge-data` chứa `config.json`, `.secret_key`, SQLite, cache LLM, Chroma và log.
  - Volume `storyforge-output` chứa ảnh, export và checkpoint.
  - Đường dẫn user store bị gỡ cùng auth (xem 4.1).
- **Image dựng sẵn:** một workflow `release.yml` chạy khi push tag `v*`, build và đẩy 2 image lên GHCR cho `linux/amd64` và `linux/arm64`. Lần push đầu cần chủ dự án đồng ý.
- **Mục tiêu kích thước:** image `api` dưới 2,5 GB (torch CPU khoảng 700 MB). Builder ghi lại con số thực tế.

### 4.5 CI và test

- **`.github/workflows/ci.yml`** chạy trên mỗi push/PR, `ubuntu-latest`. Gồm:
  - `ruff check`: cấu hình ruff thêm vào `pyproject.toml`, chỉ bật các rule chạy được với code hiện tại. Ruff thêm vào `requirements-test.txt`.
  - `pytest -m "not calibration and not bench and not perf"` với Python 3.12, cài từ lockfile, giữ ngưỡng coverage.
  - Frontend: `npm ci`, `tsc --noEmit`, `eslint`, `vitest run`.
  - `pip-audit` và `npm audit --omit=dev --audit-level=high`.
  - `docker compose build` (không push) để bắt lỗi Dockerfile.
- **Dependabot:** bật cho pip, npm, github-actions và docker.
- **Coverage filler:**
  - Rà 23 file `tests/*coverage*.py`.
  - Test chỉ assert `is not None`, `or True`, `assert True`, hoặc bọc assert trong `try/except: pass` thì viết lại thành assert hành vi nếu đáng giá, còn không thì xóa.
  - Ngưỡng coverage hạ xuống đúng mức thật sau khi dọn (không thấp hơn 60%). Ghi con số trước và sau.
- **E2E fake LLM (`test_e2e_pipeline.py`):**
  - Prompt không khớp thì phải fail thay vì trả về nội dung chương.
  - Bỏ mock Layer 3.
  - Assert `status == "completed"`.
- **Flaky:** các assert theo thời gian thực (<0,28 s, <0,35 s) đổi sang so sánh tương đối hoặc dùng đồng hồ giả. Bỏ `sleep` thật trong test.
- **Gỡ `scripts/run_gate_chunks.ps1`** khi CI chạy một process đã ổn định.

### 4.6 Gỡ các provider dùng phiên web

Gỡ toàn bộ:
- Code: `flowkit_extension/`, `api/flowkit.py`, `services/media/qwen_local_client.py`, `services/media/codex_image_client.py`.
- Phần liên quan trong `image_generator.py`, `config_routes.py`, `config/defaults.py`.
- Frontend: `FlowkitSettings.tsx`, `QwenLocalSettings.tsx`.
- Test: `test_flowkit.py`, `test_qwen_local_provider.py`, `test_codex_image_client.py`, `settings-qwen-local.spec.ts`.
- Script và docs: `scripts/eval_codex_comic.py`, `docs/flowkit-integration.md`, `docs/qwen-local-provider.md`, `docs/chatgpt-*.md`, `docs/journals/*flowkit*`, `data/flowkit/`.

Hành vi sau khi gỡ:
- **Config cũ** có `image_provider` thuộc nhóm bị gỡ thì khi load sẽ tự chuyển về `none`, ghi một cảnh báo vào log và hiện một lần trong Settings. Các key cấu hình liên quan bị bỏ qua khi đọc.
- **Comic:** pipeline comic phải vẫn chạy được với `dalle`, `seedream`, `huggingface` và `none`. Nếu có chỗ comic hard-code provider bị gỡ, builder chuyển sang dùng provider đang được cấu hình và ghi lại tính năng nào bị mất (ví dụ sửa ảnh tham chiếu).

Lỗ hổng HIGH "đọc file tùy ý qua FlowKit" tự hết khi gỡ. Builder vẫn phải rà các trường config khác nhận đường dẫn file và giới hạn chúng trong `data/` hoặc `output/`.

### 4.7 Tài liệu và dọn repo (giai đoạn 2)

- **README.md và README.vi.md:**
  - Quick Start chỉ còn Docker.
  - Mục "Phát triển" cho người đóng góp.
  - Bảng provider mới.
  - Số agent đúng thực tế.
  - Thêm tính năng comic.
  - Bảng route đầy đủ.
  - Python 3.11+.
  - Phần cảnh báo chi phí API.
- **CONTRIBUTING.md:** viết lại theo code thật: cách chạy dev, test, lint, quy ước commit, cấu trúc thư mục. Bỏ các quy định sai.
- **Script dev đa nền tảng:**
  - `scripts/dev.py` (stdlib) chạy backend và `next dev` song song, gom log, Ctrl+C tắt cả hai.
  - Giữ `dev.ps1` như một lớp mỏng gọi `dev.py`, hoặc xóa (builder chọn).
- **AGENTS.md:**
  - Viết lại ngắn gọn cho mọi coding agent.
  - Không bắt buộc Serena; nếu nhắc thì chỉ là gợi ý.
  - Không còn đường dẫn cá nhân, không mâu thuẫn về `api/v1`, số liệu đúng.
- **ARCHITECTURE.md:** cập nhật theo cây thư mục thật. Gộp `REPO_GRAPH_TREE.md` vào hoặc xóa nó (builder chọn, ưu tiên ít file hơn).
- **Đường dẫn cá nhân `C:\Users\Admin\...`:** xóa khỏi mọi file. Xóa `scripts/convert_*_to_codex.ps1`, vốn là tooling cá nhân.
- **Tài liệu nội bộ:**
  - Chuyển `worklog.md`, `IMPLEMENTATION_PLAN.md`, `TEST_PLAN.md`, `docs/journals/` cùng các spec và plan đã xong (`*-plan.md`, `*-spec.md`, `*-proposal.md`, `*-blueprint.md`) sang `docs/archive/`.
  - Giữ ADR trong `docs/adr/`. Giữ `docs/superpowers/` cho thiết kế và plan mới.
- **Tài liệu deploy:** viết lại `docs/deployment-production.md` thành `docs/self-hosting.md`, gồm: Docker, backup volume, nâng cấp image, mở LAN bằng token.
- **SECURITY.md:** thay email placeholder bằng GitHub Security Advisories ("Report a vulnerability"). Mô tả mô hình bảo mật local.
- **CHANGELOG:** thêm mục `v1.1.0` (hoặc `v2.0.0` vì gỡ auth và provider; builder đề xuất, chủ dự án quyết lúc gắn tag).
- **Cấu hình rác:** sửa `.coveragerc` và `pyproject` (mutmut, ghi chú "enforced in CI").
- **Frontend:** bỏ byte NUL trong `hooks/useStoryAvatars.ts`, sửa mojibake trong `ApiKeysFormFields.tsx`.
- **Không động tới lịch sử git** (107 MiB). Muốn làm gọn bằng `git filter-repo` thì là quyết định riêng, phải hỏi chủ dự án.

## 5. Ràng buộc

- Mỗi thay đổi là một commit nhỏ trên nhánh `release/local-open-source`, theo Conventional Commits, có trailer Co-Authored-By.
- Không push, không tạo PR, không đẩy image khi chủ dự án chưa đồng ý.
- Test hành vi hiện có phải tiếp tục pass. Bug fix nào cũng có test viết trước, và test đó phải fail trên code cũ.
- Phải xác minh trên Windows (máy chủ dự án) bằng Docker Desktop, và trên Linux bằng CI.
- Không đổi prompt, ngưỡng chất lượng hay luồng sinh truyện.

## 6. Để builder tự quyết

- Thứ tự commit trong mỗi giai đoạn. Đề xuất: phụ thuộc → CI → gỡ provider → bảo mật → bug → Docker → tài liệu.
- Tên chính xác của biến môi trường mới, nếu cần khác so với ở trên.
- Giữ hay xóa `dev.ps1` và `REPO_GRAPH_TREE.md`.
- Phương án proxy SSE (rewrites hay route handler) sau khi đã thử nghiệm.
- Chọn bộ rule ruff.
- Cách giữ `unsafe-inline` trong CSP.

## 7. Câu hỏi đã chốt sau builder check

Các quyết định dưới đây ghi đè lên phần nào ở trên mâu thuẫn với chúng.

**Chủ dự án quyết:**
- **Chỉ dùng SQLite.**
  - Gỡ Postgres, Redis và Alembic: `requirements-db.txt`, `alembic/`, `alembic.ini`, rate limiter dùng Redis, checkpoint store và cache dùng Redis, cùng mọi nhánh `REDIS_URL` và `STORYFORGE_REDIS_REQUIRED`.
  - Rate limit, session và cache chỉ còn bản trong bộ nhớ hoặc SQLite.
  - Bảng được tạo bằng `create_all` trên SQLite. Bỏ bảng `users` và các khóa ngoại `user_id` (`stories`, `pipeline_runs`) trong model, không viết migration.
  - Builder phải sửa chỗ lệch driver: `orchestrator_layers.py:49` và `health_routes.py:50` cần engine đồng bộ. Hướng sửa là dùng chung một cấu hình `STORYFORGE_DB_PATH`, rồi tự dựng URL `sqlite:///` cho engine đồng bộ và `sqlite+aiosqlite:///` cho engine bất đồng bộ, không để người dùng tự đặt `DATABASE_URL`.
- **Không chuyển dữ liệu cũ.** Bản Docker bắt đầu từ volume trống. Không viết bước import, không cần tương thích cách dẫn khóa cũ (SHA-256 từ `STORYFORGE_SECRET_KEY`). `secret_manager` chuyển hẳn sang khóa Fernet tự sinh ở `data/.secret_key`. Biến môi trường `STORYFORGE_SECRET_KEY`, nếu đặt, sẽ ghi đè khóa tự sinh.

**Claude quyết (chủ dự án duyệt khi duyệt tài liệu):**
- **Chặn lộ ra LAN khi chạy Docker:**
  - Compose đặt `STORYFORGE_IN_CONTAINER=1`. Khi biến này bật, guard "host không phải loopback mà không có token" chỉ ghi cảnh báo thay vì dừng.
  - Lớp bảo vệ trong Docker là việc compose chỉ publish cổng ra `127.0.0.1`, cộng với kiểm Host/Origin.
  - `docs/self-hosting.md` ghi rõ: muốn mở ra LAN thì đổi cổng **và** đặt `STORYFORGE_ACCESS_TOKEN`.
  - Ngoài Docker, guard vẫn dừng như ở 4.1.
- **Gỡ luôn preset "Gemini Web (local/dev)"** (`config/presets.py:59-65, 183-221`), cùng mọi preset, card UI, test và docs của bridge điều khiển trình duyệt Gemini/Qwen. Lý do: cùng loại rủi ro với các provider ở 4.6.
- **LLM chạy local trên máy chủ (Ollama, LM Studio, vLLM) phải dùng được từ Docker:**
  - Service `api` có `extra_hosts: ["host.docker.internal:host-gateway"]`.
  - `url_validator` chỉ ngoại lệ đúng hostname `host.docker.internal`, các IP private khác vẫn bị chặn.
  - Preset Ollama trong Docker trỏ tới `http://host.docker.internal:11434/v1`.
  - README có một mục ngắn về việc này.
- **Build hay pull image:**
  - `compose.yaml` mặc định **build từ source**: có `build:`, `image:` chỉ là tên local `storyforge-api` / `storyforge-web`, không có registry. Như vậy clone nhánh nào chạy đúng code nhánh đó.
  - Image GHCR nằm trong một file riêng `compose.release.yaml` (chỉ có `image: ghcr.io/...:${STORYFORGE_VERSION}`, không `build:`), được README giới thiệu sau khi có release đầu tiên.
  - `release.yml` không nằm trên đường găng của tiêu chí thành công số 1.
- **Link chia sẻ ở chế độ token:** `GET /api/share/gallery` và `GET /api/share/{id}` được miễn token, vì chia sẻ là hành động chủ động của người dùng. Mọi route còn lại trong `/api/*` và `/media/*` (trừ `/api/health`) cần token. Danh sách miễn trừ nằm ở một chỗ duy nhất và có test.
- **Phạm vi thay `require_access`:** 17 file nguồn đang dùng `require_permission`, cộng `ab_routes.py` và `feedback_routes.py` dùng `get_current_user`. Router nào chưa có dependency nào thì thêm `require_access` ở cấp router.
