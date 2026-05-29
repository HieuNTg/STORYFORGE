# SSE + Pipeline Bug Fix Plan

> Nguồn: rà soát đa-agent độc lập (API/pipeline correctness · SSE state-machine/concurrency · React/SSE client), 2026-05-29.
> Cross-check chéo UI + API + tests. Tổng: **5 Critical · 6 High · 6 Medium · 3 Low**.
> Tất cả nhóm Critical hiện **chưa có test bao phủ**.

## Nguyên tắc thực thi
- Mỗi PR phải kèm test tái hiện bug (red) trước khi fix (green). Không fix Critical nào mà không có test.
- Không đổi contract API ở PR-1/PR-2. Thay đổi kiến trúc (PR-3) tách riêng.
- Trước khi sửa bất kỳ symbol nào: `find_referencing_symbols` để lấy danh sách callsite (theo CLAUDE.md).
- L1/L2 strict-lane: không gộp state, không chia sẻ job-id giữa hai pipeline.

## Đã xác nhận KHÔNG phải bug (không đụng vào)
- L1/L2 cross-contamination: mỗi job có `PipelineOrchestrator()` riêng; FE store tách biệt. Strict-lane giữ vững.
- `jobs.db*` (FlowKit SQLite) độc lập với job registry in-memory — không có DB race, không có "mất job khi restart" (by design).
- Path traversal checkpoint load/delete đã phòng thủ đúng.
- Thứ tự terminal-state ở `/run` (`task.done()` flip sau `finally`) — không race.

---

# PR-1 — Silent-failure & event-drop trên `/run` + `/resume` (rủi ro thấp, không đổi contract)

**Mục tiêu:** vá regression progress UX + dừng việc báo "done" cho run thất bại. Đây là leverage cao nhất, gọn trong vài file.

### TASK 1.1 — [C1] Vòng drain SSE không được vứt `log` events
- **File:** `api/pipeline_routes.py:546-554` (`/run`) và `:763-769` (`/resume`)
- **Việc cần làm:**
  - Sửa vòng coalescing: CHỈ collapse các frame `stream` liên tiếp về frame mới nhất. Mọi `log` và `error` drained phải được giữ và yield theo thứ tự.
  - Cách an toàn: buffer các item drained vào list, emit tuần tự; chỉ khi gặp nhiều `stream` mới ghi đè lấy cái cuối.
  - Áp dụng cho CẢ hai endpoint (`/resume` hiện drop sạch log vì không có stream).
- **Acceptance:**
  - Khi nhiều `log` xếp hàng giữa 2 lần `get` (0.2s), tất cả `log` đều tới client đúng thứ tự.
  - `/resume` không còn drop log.
- **Test:** unit test bơm queue với chuỗi `[log, log, stream, log, stream]` → consumer nhận đủ 3 log + 1 stream cuối, đúng thứ tự.

### TASK 1.2 — [C2] Pipeline lỗi (`output.status == "error"`) bị báo là `done`
- **File:** `api/pipeline_routes.py:500-518` (`_run_async`); tham chiếu `pipeline/orchestrator_layers.py:442-444`
- **Việc cần làm:**
  - Trong `_run_async`, coi `output is not None and output.status == "error"` là failure: rút `final_error` từ `output` (hoặc log lỗi cuối) và truyền vào `mark_done`.
  - (Tùy chọn) thêm `status` vào `build_output_summary` (`api/pipeline_output_builder.py`) để FE phân biệt.
- **Acceptance:** LLM unreachable → SSE phát `error` (không phải `done` rỗng); `GET /run/{sid}` trả `status:"error"` + message thật.
- **Test:** mock `run_full_pipeline` trả output `status="error"` → job kết thúc `error`, summary mang lý do.

### TASK 1.3 — [H3] Lý do lỗi cụ thể bị mất → luôn báo "Pipeline produced no output."
- **File:** `api/pipeline_routes.py:487-516` (`/run`) và `:701-738` (`/resume`)
- **Việc cần làm:**
  - Bắt message cụ thể của từng nhánh `except` (ConnectionError / ValueError / Exception) vào biến local `caught_error`.
  - Trong `finally`, ưu tiên `caught_error` trước fallback generic khi build `final_error`.
- **Acceptance:** disconnect giữa lúc `ConnectionError` → `GET /run/{sid}` trả message thật, không phải generic.
- **Test:** mỗi nhánh except → `mark_done` nhận đúng message tương ứng.

### TASK 1.4 — [M-probe] Gỡ probe re-raise trong `_log`
- **File:** `pipeline/orchestrator_layers.py:401-409` (`[PROBE-OLOG]`)
- **Việc cần làm:** xóa code debug; nuốt + log exception từ `progress_callback`, KHÔNG `raise`. Progress emission không bao giờ được phép abort pipeline.
- **Acceptance:** callback ném exception → pipeline vẫn chạy tiếp; không spam INFO mỗi dòng "Layer 1 hoàn tất".
- **Test:** inject callback raise → `run_full_pipeline` vẫn hoàn tất.

---

# PR-2 — Job-registry lifecycle & FE terminal handling (rủi ro thấp/vừa)

### TASK 2.1 — [H1/Code#4] Reaper tasks fire-and-forget có thể bị GC hủy
- **File:** `api/pipeline_routes.py:87-89` (`start_session_reaper`), `api/pipeline_job_registry.py:109-111` (`start_job_reaper`)
- **Việc cần làm:**
  - Lưu handle 2 reaper vào biến module-level (hoặc set có done-callback) để giữ strong reference suốt vòng đời app.
  - Thêm chúng vào tập task được track và cancel/await trong `on_shutdown` (`app.py:271-286`).
- **Acceptance:** reaper không bị GC; shutdown không còn warning "Task was destroyed but it is pending".
- **Test:** sau khi start, handle reaper không `None` và được track; shutdown hủy sạch.

### TASK 2.2 — [H2] Job kẹt `running` mãi mãi → reaper không evict
- **File:** `api/pipeline_job_registry.py:97-101` (logic reaper), `:66`, `:88-89`
- **Việc cần làm:**
  - Reaper evict thêm theo tuổi khi `completed_at is None`: `now - created_at > JOB_RETENTION_SECONDS and (job.task is None or job.task.done())`.
  - Belt-and-suspenders: `task.add_done_callback` force-mark job terminal nếu worker thoát mà chưa gọi `mark_done`.
- **Acceptance:** job có task đã done nhưng kẹt `running` quá hạn → bị evict; không leak.
- **Test:** giả lập job `running` với task done quá hạn → reaper dọn.

### TASK 2.3 — [M-cancelled] Status `cancelled` không bao giờ được set
- **File:** `api/pipeline_job_registry.py:27, 82-89` (`mark_done`), `api/pipeline_routes.py:484-486`
- **Việc cần làm:**
  - Bắt `CancelledError` trong `finally` của `_run_async`, gọi `mark_done(..., status="cancelled")` (mở rộng `mark_done` nhận status tường minh).
  - Bổ sung `"cancelled"` vào union status FE (`TheaterPanel`, `usePipelineStore`).
- **Acceptance:** run bị cancel/shutdown → status `cancelled`, không bị gán nhầm `error`.
- **Test:** cancel task → job `cancelled`.

### TASK 2.4 — [M-lock] `get_run_status` đọc field không lock (torn read)
- **File:** `api/pipeline_routes.py:631-646`, `api/pipeline_job_registry.py:82-89`
- **Việc cần làm:** trong `mark_done` set `summary`/`error`/`completed_at` TRƯỚC khi flip `status`; hoặc snapshot dưới `_JOBS_LOCK` ở `get_run_status`.
- **Acceptance:** không có cửa sổ đọc `status="done"` mà `summary=None`.
- **Test:** review thứ tự gán (khó test runtime; assert thứ tự field write).

### TASK 2.5 — [C5] `onError` fire 2 lần mỗi lần stream lỗi
- **File:** `frontend/lib/sse/usePostStream.ts:123-132`
- **Việc cần làm:** thêm `settledRef = useRef(false)`; flip `true` ở terminal callback đầu tiên (`onclose`/`onerror`/`.catch`); mọi nhánh sau bail nếu đã settled. Bỏ phụ thuộc vào `controller.signal.aborted` (vì lib abort internal controller).
- **Acceptance:** kill backend giữa stream → `onError`/`toast.error` chạy đúng 1 lần.
- **Test:** RTL/Vitest mock fetch-event-source ném lỗi → handler gọi 1 lần.

### TASK 2.6 — [H5] `interrupted` sticky + `hydratedRef` chết ở run thứ 2
- **File:** `frontend/components/pipeline/PipelineScreen.tsx:113-126, 137-144, 218-234`
- **Việc cần làm:** reset `hydratedRef.current=false` (và clear `startedAt`/`resultStory` cũ) trong `onSubmit` trước `start()`; hoặc đổi hydrate guard key theo `sessionId`.
- **Acceptance:** chạy run #2 cùng tab (không reload) → timer/hydrate hoạt động đúng; không hiện state interrupted cũ.
- **Test:** mô phỏng 2 submit liên tiếp → state run #2 sạch, hydrate chạy lại.

### TASK 2.7 — [H6] Phase-1 progress kẹt dưới 100% lúc done
- **File:** `frontend/stores/theater-store.ts:535-551` (`applyDone`), `PhaseTimeline.tsx:76-83`
- **Việc cần làm:** trong `applyDone`, force `phaseStats[1].current = total` (mirror phase-2 freeze) và clear sub-label per-chapter cũ.
- **Phụ thuộc:** TASK 1.1 (drop log) là nguyên nhân gốc làm thiếu count; fix này là phòng vệ phía client.
- **Acceptance:** lúc `done`, phase-1 hiển thị 100%/đủ N chương.
- **Test:** dispatch `done` sau khi thiếu 1 log chương → phase-1 vẫn về total.

---

# PR-3 — Migrate continuation/branch SSE sang job-registry pattern (thay đổi kiến trúc, tách riêng)

> Đây là gói lớn nhất, đáng 1 sprint riêng. Pattern tham chiếu: `/run` (job registry + heartbeat + no-cancel-on-disconnect).

### TASK 3.1 — [C3] `/continue`, `/regenerate`, `/insert`, `/write-from-outlines` cancel `to_thread` không hủy được & vứt kết quả
- **File:** `api/continuation_routes.py:262-265, :422, :635, :796, :972`
- **Việc cần làm:**
  - Bỏ `task.cancel()` trên disconnect; thay bằng `return` và để worker hoàn tất, persist state ở `finally`.
  - Đăng ký job vào `pipeline_job_registry` cho cả 4 generator.
  - Thêm endpoint poll/recovery `GET .../{session_id}` tương tự `/run/{sid}`.
- **Acceptance:** disconnect giữa continuation → reload phục hồi được kết quả; worker không bị vứt.
- **Test:** giả lập disconnect → job vẫn tới terminal, poll trả kết quả.

### TASK 3.2 — [C4] `/choose/stream` blocking generator trong event loop + thiếu disconnect/heartbeat
- **File:** `api/branch_routes.py:312-318`
- **Việc cần làm:**
  - Đẩy `llm.generate_stream(...)` qua `asyncio.to_thread` feeding một `asyncio.Queue` (giống `/run`).
  - Thêm `request.is_disconnected()` poll + `: ping` heartbeat.
  - Đảm bảo luôn phát terminal frame (`complete`/`error`) trên mọi nhánh thoát.
- **Acceptance:** generate branch không khóa event loop; client khác không bị đói; disconnect dừng được; luôn có terminal frame.
- **Test:** chạy đồng thời `/choose/stream` + `/run` → `/run` không bị chặn; disconnect → generator dừng.

### TASK 3.3 — [H4] Queue progress unbounded phình sau disconnect
- **File:** `api/pipeline_routes.py:537-542`, `api/pipeline_job_registry.py:40`
- **Việc cần làm:** đặt `maxsize` cho queue + producer drop/coalesce khi đầy; HOẶC consumer set flag disconnect để producer ngừng enqueue (logs list đã giữ đủ cho recovery).
- **Acceptance:** sau disconnect, bộ nhớ queue không tăng vô hạn đến lúc reap.
- **Test:** disconnect + worker tiếp tục emit nhiều log → queue bị bound, không OOM.

### TASK 3.4 — [M-shutdown] Shutdown để lại `to_thread` worker + nuốt timeout
- **File:** `api/pipeline_routes.py:92-98` (`shutdown_pipeline_tasks`), `app.py:274`
- **Việc cần làm:** log tập task còn pending sau timeout 30s; checkpoint write atomic (write-temp-then-rename); document rằng L1 in-flight không hard-cancel được, dựa vào registry để recover sau restart.
- **Acceptance:** shutdown không ghi checkpoint hỏng; tập pending được log.
- **Test:** giả lập shutdown khi đang ghi checkpoint → file không bị cắt cụt.

### TASK 3.5 — [M-FE-audit] Audit mọi consumer `usePostStream` cho terminal-flip
- **File:** mọi nơi gọi `usePostStream` (continuation/regenerate/insert FE screens)
- **Việc cần làm:** đảm bảo từng consumer flip terminal state trong CẢ `onClose` lẫn `onError` (commit gốc chỉ chạm `PipelineScreen` + `useBranchSession`).
- **Acceptance:** không screen nào còn treo timer khi stream kết thúc bất thường.
- **Test:** mỗi screen → mock close/error → state về terminal.

---

# PR-4 — Cleanup Medium/Low (gom 1 lượt)

### TASK 4.1 — [M-unwrap] `done` frame double-unwrap brittle
- **File:** `frontend/lib/sse/pipelineBridge.ts:76-87`
- **Việc cần làm:** unwrap MỘT lần trong bridge, truyền object inner chuẩn cho cả `applyDone` và `onDone`. Loại bỏ `p.data ?? p` rải rác.
- **Test:** done frame shape hiện tại + shape nested thêm 1 lớp → cả hai path nhận đúng `draft.chapters`.

### TASK 4.2 — [M-chapter-scope] Chapter-scoping clamp + genre-bump ghi đè
- **File:** `frontend/components/pipeline/PipelineForm.tsx:122-145, 279-300`
- **Việc cần làm:**
  - Thêm effect clamp `chapters_this_session` khi hạ `num_chapters` (giống `ContinueStoryScreen.tsx:66-68`).
  - Thay heuristic value-equality bằng dirty-flag "user đã chạm num_chapters" để genre-bump không nuốt giá trị user.
- **Test:** hạ num_chapters dưới chapters_this_session → clamp live; user set num_chapters thủ công rồi đổi genre → không bị ghi đè.

### TASK 4.3 — [L-toctou] TOCTOU rate-limit IP
- **File:** `api/pipeline_routes.py:368-377`, `:677-686`
- **Việc cần làm:** gộp count + insert vào MỘT lần acquire `_orchestrators_lock`.
- **Test:** N request đồng thời cùng IP → không vượt `_MAX_SESSIONS_PER_IP`.

### TASK 4.4 — [L-thread-churn] Polling queue bằng `to_thread(get, timeout=0.2)`
- **File:** `api/pipeline_routes.py:544, :762`
- **Việc cần làm:** cân nhắc `asyncio.Queue` feed qua `loop.call_soon_threadsafe`, hoặc executor nhỏ riêng. (Optimization, không phải correctness — làm nếu PR-3 đã chạm vùng này.)

### TASK 4.5 — [L-eventsource] `useEventSource` reconnect-storm footgun (dead code)
- **File:** `frontend/lib/sse/useEventSource.ts:53-56`
- **Việc cần làm:** XÓA file (không nơi nào import) hoặc vá `handleError` để `close()` khi không phải terminal. Khuyến nghị: xóa.

### TASK 4.6 — [L-sqlite] `busy_timeout` chỉ set lúc init
- **File:** `services/media/flow_service.py:176, 185-187, 193-195`
- **Việc cần làm:** set `PRAGMA busy_timeout` trong `_db_execute_sync`/`_db_query_sync`, hoặc dựa hẳn vào `timeout=` và bỏ PRAGMA gây hiểu nhầm ở init. (Không phải bug sống.)

---

# Bảng tổng hợp & thứ tự ưu tiên

| PR | Tasks | Severity | Đổi contract? | Ưu tiên |
|----|-------|----------|---------------|---------|
| PR-1 | 1.1 C1, 1.2 C2, 1.3 H3, 1.4 probe | 2 Critical + 1 High + 1 Med | Không | **1 (ngay)** |
| PR-2 | 2.1 H1, 2.2 H2, 2.3–2.4 Med, 2.5 C5, 2.6 H5, 2.7 H6 | 1 Critical + 3 High + 2 Med | Không | **2** |
| PR-3 | 3.1 C3, 3.2 C4, 3.3 H4, 3.4–3.5 Med | 2 Critical + 1 High + 2 Med | **Có** (thêm endpoint) | **3 (sprint riêng)** |
| PR-4 | 4.1–4.6 | Med + Low | Không | **4 (cleanup)** |

**Định nghĩa Done toàn cục:** mọi Critical/High có test red→green; `pytest` + `vitest` xanh; không regression strict-lane L1/L2; cập nhật CHANGELOG.
