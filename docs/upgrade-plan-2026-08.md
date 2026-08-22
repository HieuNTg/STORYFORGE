# Lộ trình nâng cấp StoryForge — 22-08-2026

Kết quả tổng rà soát toàn bộ mã nguồn (~770 file backend + frontend, đọc sâu theo 7 phân hệ: L1, L2/agents, LLM services, Media/Comic, API/Config, Frontend, Tests/Ops) và kế hoạch tối ưu – nâng cấp theo 5 giai đoạn. Mọi phát hiện đều có file:line.

**Số liệu tổng quan:**

| Chỉ số | Giá trị |
|---|---|
| Lỗi P0 — sản phẩm đang gãy âm thầm | 14 |
| Chi phí LLM của L2 có thể cắt | ~50–70% |
| Dead code có thể xóa | ≈15.000 dòng |
| Coverage thật | 70% (nhưng gate không bao giờ fail) |

**Kết luận tổng quát.** Kiến trúc lõi (2-layer pipeline, fallback chain, checkpoint, SSE + recovery, comic compositor) đúng hướng và khá trưởng thành. Vấn đề nằm ở 3 nhóm: (1) một loạt tính năng chủ lực **chết âm thầm** — lỗi bị nuốt, log vẫn báo xanh; (2) chi phí/thời gian chạy LLM cao gấp nhiều lần mức cần thiết; (3) trầm tích lớn từ các lần pivot (Veo/video, Gradio, Alpine, DB layer) chưa dọn. Đề xuất: **không tái kiến trúc** — sửa đúng thứ tự dưới đây, mỗi giai đoạn một sprint branch → một PR.

---

## Giai đoạn 0 — Vá những chỗ đang gãy âm thầm (1 sprint, 14 mục)

1. **[L2] Toàn bộ lane phê bình craft (8 agents + debate) chết trong config mặc định.** `agent_registry.py:243` đọc `cfg.debate_mode` — field không tồn tại trên `PipelineConfig`. AttributeError bị nuốt thành `[AGENTS] WARN`, vứt bỏ toàn bộ review và bỏ đói SmartRevision. → Thêm field vào `config/defaults.py` (1 dòng) + test khẳng định review cycle chạy trên default config.

2. **[L2] Contract gate sau L2 không bao giờ hoạt động — log vẫn báo "✅ 0 vi phạm".** `scene_enhancer.py:411-418` dựng lại `Chapter` làm rơi `contract`/`structured_summary` → gate (`contract_gate.py:296`) thấy None ở mọi chương. `_post_gate_validate` đọc thuộc tính không tồn tại nên luôn True. → Mang 2 field theo khi tái tạo Chapter.

3. **[L2] Một lỗi LLM ở cuối mô phỏng vứt bỏ toàn bộ L2.** `evaluate_drama`/`_generate_suggestions` (`simulator.py:1171, 1252`) không bọc lỗi — call #91 fail là ~90 call trước đó bị vứt, ship bản L1 thô với drama_score=0. → Bọc + degrade (dùng điểm round trước), cảnh báo rõ lên SSE.

4. **[Config] Backend không bao giờ load `.env` — API key đang lưu plaintext.** Không có `load_dotenv` ở đâu cả → `STORYFORGE_SECRET_KEY` không set → mã hóa secrets không chạy (đã xác nhận plaintext trong `data/config.json`); 30 env override trong `_ENV_MAP` chết. → Gọi `load_dotenv()` sớm trong `app.py`, migrate + re-encrypt; sửa luôn crash khi `DATABASE_URL` dùng sync driver (`database.py:159`).

5. **[Config] Restart mất một nửa cấu hình; lưu Settings xóa field lạ.** `save_config` chỉ ghi 103/244 field — toàn bộ `l2_*` (26 field), `enable_agent_debate`, `parallel_chapters_enabled`, budget caps… revert về default khi restart. Field có trong `config.json` nhưng vắng trong writer bị xóa ở lần lưu kế. Preset áp một nửa. 9 cặp default mâu thuẫn giữa `defaults.py` và `persistence.py` (vd `panels_max` 24 vs 12, `flowkit_aspect_ratio` 4:5 vs 9:16). → Sinh save/load tự động từ dataclass (`asdict` + exclude list), xóa mọi `getattr(..., default)` chết.

6. **[Frontend] Thư viện có thể mất trắng khi localStorage đầy — UI vẫn báo "đã lưu".** `library-store.ts:201-233` không bắt `QuotaExceededError`; state RAM đã mutate nên toast thành công vẫn hiện, reload là mất. Throw còn nổ trong SSE callback làm treo panel lúc done. → Bắt lỗi persist + toast thật; tách prose sang IndexedDB; bọc `commitToLibrary` ngoài luồng SSE.

7. **[Frontend] Đứt stream là mồ côi run — recovery không bao giờ bật.** Poller bị gate bởi `pendingBody` (`PipelineScreen.tsx:242`); Cancel không báo backend nên recovery "hồi sinh" run đã hủy; replay từ cursor 0 bắn 12 toast; poller bỏ cuộc vĩnh viễn sau 5 lỗi; flow "Viết tiếp" không có recovery. → Clear `pendingBody` trong onError; gửi cancel về backend; replay im lặng; backoff; áp cùng cơ chế cho Continue.

8. **[Comic] Một panel fail làm lệch toàn bộ trang phía sau.** `image_generator.py:217-225` chỉ append panel thành công → compositor cắt theo vị trí (`page_compositor.py:1070-1078`) đẩy mọi panel sau vào sai ô. → Append sentinel None; `_place_panel` đã có placeholder. ~10 dòng.

9. **[LLM] Cache key sai — L2 có thể nhận câu trả lời cache của L1.** Key đọc dùng model cấu hình, key ghi dùng model thực (`client.py:747 vs 834`) → gần như không hit sau fallback + nhiễm chéo layer; `max_tokens` không trong key. → Model thực + max_tokens vào key; namespace theo layer.

10. **[L1] Checkpoint từng chương ghi nhưng không bao giờ đọc — crash giữa chừng mất sạch.** `resume_from_chapter` 0 call site; `resume()` chạy thẳng L2 trên draft dở dang (crash chương 7/20 → ship 7 chương như "hoàn chỉnh"); save là daemon thread fire-and-forget. → Nối `resume_from_batch`; so `len(chapters)` với `len(outlines)`; await ghi thật ở ranh giới layer.

11. **[API] Flags mỗi run ghi đè config toàn cục.** `pipeline_routes.py:767-810` mutate singleton; nhánh else chỉ bật không tắt (bỏ tick vô tác dụng); Settings save persist luôn flags tạm của run. → Snapshot config per-run.

12. **[L2] Lỗi transient khi chấm điểm bị coi là "trượt" → re-enhance cả chương + revert thoại.** Validation gặp 429 trả `passed=False, score=0.0` (`chapter_contract.py:169-181`) → re-enhance ~12-15 call + revert thoại về L1 thô. → Thêm trạng thái `error` tách khỏi `failed`.

13. **[FlowKit] HTTP callback của extension bị CSRF chặn.** `/api/ext/callback` không trong danh sách miễn (`middleware/csrf.py:18-24`) → 403 trước khi kiểm HMAC. → Miễn CSRF (đã có HMAC).

14. **[LLM] Timeout 900s chưa phủ hết + mâu thuẫn ngưỡng cũ.** Anthropic/Gemini bỏ qua `request_timeout` + giữ SDK retry nội bộ; `stream_first_chunk_timeout=180` giết đúng ca chậm; `fallback_max_latency_ms=120s` blacklist model chậm hợp lệ. → Truyền timeout + `max_retries=0`; đồng bộ 2 ngưỡng.

---

## Giai đoạn 1 — Cắt chi phí và thời gian chạy LLM (1–1,5 sprint)

Một run 10 chương hiện tốn **450–700 call** (1.200+ nếu quality gate retry). Mục tiêu: −50% chi phí, −40% thời gian.

**Lặp việc — xóa call thừa:**
- Voice engine build lại mỗi chương + retry (~50+ call trùng) → cache process-level giết ~90% (`enhancer.py:342/545/665/707`).
- Retry contract/voice chạy lại nguyên scene-pipeline của chương (`enhancer.py:550-562, 669-681`) → chỉ re-enhance scene lỗi.
- Scene decomposition gọi 2 lần/chương ở đường sequential.
- Quality-gate fail regenerate cả truyện (`orchestrator_layers.py:715-726`) → dùng SmartRevision nhắm chương yếu (có sẵn).
- `generate_json` xếp chồng tới 4 lượt full-chain → giới hạn repair 1 lượt + cheap tier.

**Định tuyến model — việc rẻ dùng model rẻ:**
- Simulator (~100 call/run) chạy toàn model đắt; `evaluate_drama` (chỉ lấy 1 số) + reaction chain là ứng viên cheap-tier rõ nhất (`simulator.py:560/692/952`).
- Panel 8 agents × 3 vòng không max_tokens, không cheap-tier dù chỉ trả JSON nhỏ.
- Judge chấm 6 chiều nhưng overall dùng 4; CoT reasoning trả tiền chỉ để debug-log.
- Chain cheap-tier loại luôn primary model (fail toàn tập khi cheap sập) và xếp cheap model cuối chain default.

**Song song hóa:**
- ConsistencyEngine: ~100 call rẻ tuần tự tuyệt đối → batch theo chương + gather (`character_state_registry.py:143-215`).
- `finalize_chapter`: ~10 validator tuần tự/chương → 2-3 nhóm gather (`post_processing.py`).
- Preamble L1: 6/11 call độc lập → cắt 60-90s "đứng hình" đầu run.
- Panel comic tuần tự trong chương + Reader tuần tự cả chương → FlowKit ramp không bao giờ ramp (`image_generator.py:171-226`).
- DAG agent 4 tầng → 2 tầng (chỉ editor cần prior_reviews) = cắt đôi wall-clock panel.
- `max_parallel_workers` chỉ được đọc để in log — gather thực tế không giới hạn (50 chương = 50 pipeline đồng thời + nested pools).

**Kỷ luật retry & trạng thái chia sẻ:**
- Retry nhân bản: 3 retry × chain 50–300 mục × 3 vòng → thêm deadline tổng per-call, giới hạn chain.
- Cooldown 429 bị `clear()` toàn cục giữa các vòng (`client.py:794-795`) — các chương song song phá trạng thái xoay key của nhau.
- Dùng usage tokens thật từ response thay `len//4` (lệch ~45% tiếng Việt); đường streaming (thân chương!) phải được tính tiền.
- Cache bật ở temperature sáng tác → vòng retry chất lượng nhận lại y nguyên văn cũ, không hội tụ.

---

## Giai đoạn 2 — Đại dọn dẹp ~15.000 dòng (1 sprint)

| Khối | Nội dung | ~Dòng |
|---|---|---|
| DB layer chết | DB rỗng 0 rows; `_persist_*_to_db`, diagnostics_routes, `_load_story_from_db`, ORM + alembic cho tính năng không dùng | ≈1.100 |
| Route modules chết | 12 module không FE nào gọi (ab, analytics, auth, dashboard-luôn-500, diagnostics, eval, feedback, metrics, prompt, quality, branch_websocket, health/deep) + 10/12 endpoint continuation | ≈2.500 |
| Veo/video sót | `request_video`, bảng SQLite `flow_jobs` + poll loop nền mỗi 5s từ boot (`app.py:292-302`) | ≈180 + 1 bg task |
| Frontend chết | LibraryScreen/Grid/Toolbar, PipelineOverlay, ChoicePanel… + 2 route reader không có đường vào kéo theo ComicGenerator 359 dòng | ≈1.400 |
| Pipeline chết | PROBE instrumentation + heartbeat prod, MediaProducer không .run(), foreshadowing_plan wiring, DialogueSubtextAnalyzer… | ≈800 |
| plugins/ & locales/ | `load_all()` không bao giờ được gọi → hook rỗng trên hot path; locales Gradio-era trôi dạt | ≈600 |
| /api/v1 | Không client gọi; nhân đôi route table + Deprecation middleware mọi request | ≈100 |
| Trùng lặp hợp nhất | 5 bản `_detect_provider_type`; 2 bảng giá LLM; 3 model library-payload; 5 SSE generator; 6 save-handler settings; 3 limiter; 4 blob-download; 5 câu "no text" | ≈2.000 |

---

## Giai đoạn 3 — Nền tảng chất lượng (1,5 sprint)

1. **Eval framework tiếng Việt — khung có sẵn, thiếu đúng dữ liệu tiếng Việt.** `tests/benchmarks/` đã có eval_runner (LLM-judge vs human), eval_metrics (Pearson/MAE), scoring_calibration — nhưng import hỏng, không được collect, và golden dataset là 20 truyện TIẾNG ANH. Test calibration payoff VN (30 cặp, F1 ≥ 80%) bị loại khỏi mọi gate chunk — ngưỡng 0.55 đang ship không được canh gác. → Golden set 20 truyện × 5 thể loại VN; sửa import; calibration chạy hàng tuần.
2. **Gate phải biết fail.** `run_gate_chunks.ps1` luôn success (`--cov-fail-under=0`, không gom exit code); CHUNK4 collect 0 test (49s lãng phí); `.coverage` còn ~1.900 statement ma của file đã xóa. Coverage thật 70%. → Gom exit codes; erase trước append; ratchet 70%; chia chunk theo thời lượng.
3. **Hợp đồng SSE có kiểu.** Toàn bộ progress UI đang parse regex trên log prose tiếng Việt (`sniffers.ts`). → Backend phát event JSON có kiểu song song log; hợp nhất 3 thế hệ SSE về gen-3; xóa 3 endpoint còn cancel worker khi client rớt.
4. **ImageBackend Protocol.** Thêm provider ảnh hiện sửa ~8 chỗ; 2 abstraction chồng nhau; retry/timeout mỗi provider một kiểu. → Một Protocol + dispatcher retry/backoff/fallback thống nhất; gộp 3 bản "portrait nhân vật".
5. **Thực thi hợp đồng lane simulator/debate bằng code.** `_drop_cross_lane` là no-op cấu trúc (mọi role stamp "craft"); `DRAMA_DEBATE` ra lệnh ngược lane; debate reasoning chèn chuỗi thô lách validator. → Sửa lane drama_critic; thêm boundary vào 2 prompt thiếu; test lane leakage.
6. **Đồng nhất 3 đường ghi chương.** Parallel thiếu self-critique + injections so với sequential; continuation thiếu contract/finalize/length-gate/RAG. → Trích `write_one_chapter()` dùng chung.

---

## Giai đoạn 4 — Đóng gói & tài liệu (0,5–1 sprint)

- **Docker production không có UI**: frontend bị dockerignore, không service nào serve Next.js — làm theo docs là ra bản headless. Thêm stage build static export.
- Image thiếu spaCy model + MiniLM weights; không chạy `alembic upgrade`; single-stage với build-essential.
- **Docs đang dẫn agent vào crash**: AGENTS.md/ARCHITECTURE.md bảo chạy `pytest tests/ -x -v` (crash native), tả file đã xóa, Alpine.js/Gradio/TTS/Veo khắp nơi. Viết lại 2 file + dọn docs/.
- Scripts hỏng: 2 script trỏ checkpoint đã xóa; demo trỏ sai port UI; 2 script convert hard-code đường dẫn máy + destructive.
- Frontend prod: xác minh static export với 4 dynamic route thiếu `generateStaticParams`; bỏ ship cả 2 catalog i18n về client (bundle win lớn nhất); dynamic-import recharts/xyflow.

---

## Trình tự thi công

| Sprint | Giai đoạn | Nội dung |
|---|---|---|
| 1 | GĐ 0 | 14 bản vá P0, mỗi vá kèm regression test |
| 2–3 | GĐ 1 | Lặp việc → routing cheap-tier → song song hóa → kỷ luật retry; đo trước/sau bằng token tracking |
| 3 | GĐ 2 | Đại dọn dẹp (song song với cuối GĐ 1 được) |
| 4–5 | GĐ 3 | Golden set VN + gate biết fail trước, rồi SSE typed, ImageBackend, lane enforcement, hợp nhất đường ghi chương |
| 5 | GĐ 4 | Docker có UI, docs không nói dối, scripts chạy được |

**Định nghĩa Done mỗi PR:** regression test tái hiện lỗi trước khi sửa; thay đổi hiệu năng kèm số đo trước/sau; không thêm sync call trong async context; không thêm `getattr(..., default)` mới cho config; xóa dead code kèm bằng chứng không-caller (find_referencing_symbols) trong mô tả PR.
