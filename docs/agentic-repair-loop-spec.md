# Spec: Agentic Repair Loop cho L1 chapter finalize

**Trạng thái**: đề xuất, chưa duyệt
**Ngày**: 2026-08-26
**Phạm vi**: `pipeline/layer1_story/` — giai đoạn post-write của một chương
**Không đụng tới**: L2 enhance, comic pipeline, media, agent debate panel hiện có

---

## 1. Vấn đề

Sau khi một chương được viết xong, nó đi qua **5 pass sửa lỗi độc lập**, mỗi pass
tự quyết định có chạy hay không và mỗi pass **viết lại toàn bộ chương**:

| # | Pass | File | Trigger |
| --- | --- | --- | --- |
| 1 | Self-critique + rewrite weak sections | `pipeline/layer1_story/chapter_critique_runner.py:17` | `should_critique()` — chương climax/twist hoặc mỗi N chương |
| 2 | Foreshadowing payoff rewrite | `pipeline/layer1_story/chapter_payoff_rewrite.py:19` | `story_context.foreshadowing_payoff_missing` khác rỗng |
| 3 | Consistency violation rewrite | `pipeline/layer1_story/chapter_rewrites.py:18` | ≥3 name warning HOẶC ≥2 arc drift HOẶC ≥2 location warning |
| 4 | Pacing enforcement rewrite | `pipeline/layer1_story/chapter_rewrites.py:135` | classifier nói lệch nhịp với confidence ≥0.7 |
| 5 | Length gate expand | `pipeline/layer1_story/chapter_length_gate.py:63` | dưới 85% `word_count` mục tiêu |

Thứ tự thực thi cố định tại `pipeline/layer1_story/chapter_finalizer.py:97-127`
(pass 1 chạy sớm hơn, tại `pipeline/layer1_story/batch_generator.py:457`).

Cả 5 flag đều **mặc định `True`** trong `config/defaults.py:374,388,442,447,460`.

### 1.1 Bốn hệ quả đo được

**(a) Chi phí worst-case mỗi chương: 8 LLM call, trong đó 5 call sinh lại nguyên chương.**

```
critique_chapter             1 call   (đọc chương, ra JSON)
rewrite_weak_sections        1 call   <- full chapter regen
critique_chapter (rescore)   1 call   (chapter_critique_rollback, mặc định True)
rewrite_for_missing_payoffs  1 call   <- full chapter regen
rewrite_for_consistency      1 call   <- full chapter regen
verify_pacing                1 call
rewrite_for_pacing           1 call   <- full chapter regen
EXPAND_CHAPTER               1 call   <- full chapter regen, max_tokens 8192
```

Một truyện 40 chương ở worst-case là ~200 call sinh lại nội dung đã có.

**(b) Các pass ghi đè lẫn nhau.** Comment tại `chapter_finalizer.py:118-120` đã
thừa nhận: *"the rewrites above can each shorten the chapter"*. Việc đẩy length
gate xuống cuối chính là **patch cho triệu chứng**, không phải cho nguyên nhân.
Nguyên nhân là pass 2/3/4 rewrite toàn chương mà không biết ràng buộc độ dài tồn
tại. Chuỗi hỏng điển hình:

```
chương 1800 từ, target 2000
 -> payoff rewrite       -> 1500 từ (model tóm gọn khi chèn payoff)
 -> consistency rewrite  -> 1300 từ
 -> length gate: 1300 < 1700 -> expand -> 2100 từ
    nhưng lần expand này KHÔNG bị ràng buộc phải giữ payoff/consistency vừa sửa
```

Prompt `EXPAND_CHAPTER` (`chapter_length_gate.py:31`) chỉ yêu cầu "giữ NGUYÊN cốt
truyện, thứ tự sự kiện và kết chương" — không nhắc payoff hay tên nhân vật vừa
được sửa ở hai pass trước. Không có gì đảm bảo fix của pass 2 và 3 sống sót.

**(c) Chỉ pass 1 có rollback.** `chapter_critique_runner.py:82-118` re-score và
revert nếu điểm tụt. Pass 2, 3, 4, 5 **chấp nhận vô điều kiện** kết quả rewrite
miễn là khác bản gốc (`chapter_rewrites.py:95`, `chapter_rewrites.py:188`,
`chapter_payoff_rewrite.py:66`). Model trả về bản tệ hơn thì bản tệ hơn vẫn ship.

Riêng length gate có một nửa bảo vệ (`chapter_length_gate.py:142`: từ chối bản
ngắn hơn) — đúng hướng, nhưng chỉ cho một chiều của một tiêu chí.

**(d) Không pass nào biết pass khác đã chạy.** Mỗi hàm nhận `chapter`, `outline`,
`story_context` rồi tự quyết. Không có state chung ghi lại "chương này đã bị
rewrite 3 lần rồi, dừng lại".

### 1.3 Nghiên cứu nền: vì sao verifier phải là detector tất định

Tra cứu literature trước khi chốt thiết kế (2026-08-26). Ba kết luận đổi được thiết kế:

**(1) Self-correction nội sinh làm chất lượng *tệ đi*.** Khi model tự chấm bài
của chính nó mà không có tín hiệu ngoài, hiệu năng thường giảm sau vòng "sửa"
([Huang et al., *LLMs Cannot Self-Correct Reasoning Yet*](https://arxiv.org/abs/2310.01798)).
Đây chính xác là hình dạng của pass 1 hôm nay: LLM critique chương của chính nó
-> LLM rewrite -> LLM chấm lại. Việc pass 1 là pass **duy nhất** cần rollback
(`chapter_critique_runner.py:82-118`) không phải trùng hợp — nó là pass duy nhất
không có tín hiệu ngoài.

> **Nguyên tắc bắt buộc cho spec này:** verifier trong repair loop **phải** là
> detector tất định — `count_words`, `consistency_validators`, `verify_payoffs`
> (embedding), pacing classifier. **Cấm** dùng LLM-as-judge làm điều kiện dừng
> của vòng lặp. Đây là ranh giới giữa thiết kế này và một self-refine loop thông
> thường, và là lý do nó được kỳ vọng có lãi.

**(2) Verifier ngoài + vòng lặp có trần là mô hình đã được xác nhận.** Tách
generator khỏi verifier, cho verifier chỉ ra lỗi *cụ thể* thay vì chấm điểm tổng
quát, lặp tới khi verified hoặc hết retry — xem
[LLMRefine](https://arxiv.org/html/2311.09336v2) (fine-grained actionable
feedback) và [Self-Refine](https://arxiv.org/abs/2303.17651). Củng cố:
`RepairFinding.evidence` + `RepairPlan.ordered_fixes` phải mang lỗi cụ thể kèm
trích đoạn, không phải điểm số.

**(3) Lợi ích tập trung ở vòng đầu, plateau khoảng vòng 3.** Ủng hộ
`repair_max_rounds = 2`. Không nâng lên 3+ nếu chưa có số đo phản bác.

**Hệ quả trực tiếp:** câu hỏi mở "có nên tắt `chapter_critique_rollback` không?"
được trả lời — **có**, xem mục 10.1.

### 1.2 Vì sao đây đúng là chỗ agentic thắng

Đây là **repair**, không phải generation. Không gian lỗi mở (không enumerate
trước được lỗi nào xuất hiện cùng lúc), và lời giải tốt phụ thuộc vào *tổ hợp*
lỗi — thứ mà một luật `if threshold then rewrite` không biểu diễn được, còn một
bước chẩn đoán thì có.

Ngược lại, khung xương (viết chương N, extract entity, validate contract) vẫn
tất định — spec này **không đụng vào**.

---

## 2. Mục tiêu và phi mục tiêu

### Mục tiêu

| ID | Mục tiêu | Cách đo |
| --- | --- | --- |
| G1 | Gộp tối đa 5 lần regen thành **1 rewrite hợp nhất** | đếm LLM call/chương trong trace |
| G2 | Không fix nào bị pass sau xoá | verify sau rewrite kiểm lại **toàn bộ** finding |
| G3 | Ngân sách token cứng cho repair mỗi chương | vượt `repair_budget_calls` -> thoát |
| G4 | Rollback cho **mọi** repair, không riêng self-critique | so điểm tổng hợp trước/sau |
| G5 | Giữ nguyên resume / test / song song | gate chunks xanh, checkpoint không đổi schema |

### Phi mục tiêu

- Không thay planner LLM cho thứ tự stage L1/L2.
- Không đụng `pipeline/agents/` (panel debate) — hệ đó phục vụ mục đích khác.
- Không đổi schema `Chapter` / `StoryContext` / checkpoint.
- Không bỏ đường tất định — nó là fallback bắt buộc.

---

## 3. Kiến trúc

### 3.1 Chuyển đổi

```
HIỆN TẠI:  detect1 -> rewrite1 -> detect2 -> rewrite2 -> ... -> detect5 -> rewrite5

ĐỀ XUẤT:   detect1..5   (giữ nguyên, phần lớn không tốn LLM call)
              |
           RepairPlanner        (1 call)     <- mới
              |
           rewrite hợp nhất     (1 call)
              |
           re-verify toàn bộ finding (rẻ)
              |
           đạt? ship : (còn budget? lặp : fallback tất định)
```

Điểm mấu chốt: **giữ nguyên toàn bộ detector**. Chúng đã đúng, đã có test, và
phần lớn không tốn LLM call (`consistency_validators`, `count_words`,
`verify_payoffs` dùng embedding). Chỉ thay tầng *quyết định sửa gì và sửa thế nào*.

### 3.2 Module mới

```
pipeline/layer1_story/repair/
    __init__.py
    findings.py        # RepairFinding, Severity
    collector.py       # chạy detector -> list[RepairFinding], KHÔNG side-effect
    planner.py         # findings -> RepairPlan (1 LLM call)
    executor.py        # RepairPlan -> 1 rewrite call
    verifier.py        # chạy lại detector trên bản mới, so sánh
    coordinator.py     # vòng lặp + budget + fallback
    prompts.py
```

### 3.3 Contract

```python
# findings.py
from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    BLOCKER = "blocker"   # payoff thiếu, vi phạm world rule
    MAJOR = "major"       # arc drift, sai tên, lệch nhịp
    MINOR = "minor"       # thiếu độ dài, show-don't-tell


@dataclass(frozen=True)
class RepairFinding:
    source: str            # "payoff" | "consistency" | "pacing" | "length" | "critique"
    severity: Severity
    detail: str            # mô tả cho người đọc và cho model
    evidence: str = ""     # trích đoạn liên quan, tối đa 300 ký tự
    hard_constraint: str = ""   # ràng buộc phải giữ, vd "chương phải >= 1700 từ"


@dataclass
class RepairPlan:
    strategy: str              # "targeted" | "full_rewrite" | "skip"
    ordered_fixes: list[str]   # mô tả từng fix, thứ tự áp dụng
    constraints: list[str]     # gộp mọi hard_constraint — model PHẢI giữ
    rationale: str
    skip_reason: str = ""


@dataclass
class RepairOutcome:
    applied: bool
    rounds_used: int
    calls_used: int
    findings_before: int
    findings_after: int
    rolled_back: bool
    fallback_used: bool
```

`constraints` là câu trả lời cho vấn đề (b): mọi ràng buộc từ mọi detector được
gộp vào **một** prompt rewrite duy nhất, nên không fix nào có thể xoá fix khác.

### 3.4 Coordinator

```python
def repair_chapter(ctx) -> RepairOutcome:
    budget = RepairBudget(
        max_rounds=cfg.repair_max_rounds,     # mặc định 2
        max_calls=cfg.repair_budget_calls,    # mặc định 4
    )
    findings = collect_findings(ctx)
    if not findings:
        return RepairOutcome(applied=False, ...)

    baseline = snapshot(ctx.chapter)          # content + word_count
    baseline_score = score(findings)

    while findings and budget.can_continue():
        plan = plan_repair(findings, ctx, budget)      # 1 call
        if plan.strategy == "skip":
            break
        revised = execute_repair(plan, ctx, budget)    # 1 call
        if revised is None:
            break
        candidate = apply(ctx.chapter, revised)
        findings_after = collect_findings(ctx, on=candidate)
        if score(findings_after) > baseline_score + cfg.repair_regression_tolerance:
            restore(ctx.chapter, baseline)             # rollback (G4)
            return RepairOutcome(rolled_back=True, ...)
        commit(ctx.chapter, candidate)
        baseline_score = score(findings_after)
        findings = findings_after

    if findings and cfg.repair_fallback_to_legacy:
        run_legacy_passes(ctx)                # đúng 4 lời gọi hiện tại
        return RepairOutcome(fallback_used=True, ...)
    return RepairOutcome(applied=True, ...)
```

**Bất biến bắt buộc:**

1. `budget.max_calls` là trần cứng. Hết budget thì thoát, không bao giờ lặp thêm.
2. Mọi exception trong repair là **non-fatal**, giữ đúng style hiện tại
   (`chapter_rewrites.py:113`, `chapter_length_gate.py:164`) — rơi về `baseline`.
3. Baseline score phải đo bằng **cùng thước đo** với candidate. Chi tiết ở §3.6 —
   đây là chỗ bản hiện thực đầu tiên sai và bị test bắt.
4. `collect_findings` phải **thuần** khi chạy trên candidate. Đây là thay đổi
   lớn nhất so với code hiện tại: các detector đang ghi thẳng vào
   `story_context.name_warnings`, `arc_drift_warnings`,
   `foreshadowing_payoff_missing` — cần tách phần detect khỏi phần commit warning.

### 3.6 Baseline phải đo bằng cùng một thước đo (bài học từ hiện thực)

Bản đầu chấm baseline từ `findings` — tức từ các warning mà
`process_chapter_post_write` đã tính trước đó — rồi chấm candidate bằng
`recheck_findings`, tức chạy lại detector trên văn bản mới. Hai thước đo khác
nhau, và hậu quả cụ thể: một chương 1800 từ có 3 name warning bị viết lại thành
900 từ vẫn được chấm là *tốt hơn*, vì các name warning cũ không tái hiện được
trên bản mới còn lỗi độ dài mới thì nhẹ hơn tổng 3 warning cũ.

`test_repair_rollback_on_regression` bắt đúng lỗi này. Cách sửa: coordinator chạy
`recheck_findings` trên chính bản gốc để lấy baseline. Miễn phí — mọi detector
recheck được đều không dùng LLM, đó là lý do chúng được chọn.

**Hệ quả cho `RECHECKABLE_SOURCES`:** chỉ `payoff`, `name`, `location`, `length`
tham gia chấm điểm. Ba nguồn còn lại được mang theo làm ràng buộc nhưng không bao
giờ được chấm lại:

| Nguồn | Vì sao không chấm lại |
| --- | --- |
| `pacing` | đo tốn 1 LLM call — chấm lại mỗi vòng là tiêu ngân sách vào việc đo thay vì việc sửa |
| `arc` | `detect_arc_drift` đọc `story_context.character_states`, không đọc văn bản — viết lại chương không đổi được kết luận của nó |
| `critique` | LLM tự chấm văn của chính nó — đúng tín hiệu §1.3 cấm dùng làm điều kiện dừng |

### 3.5 Vì sao vẫn resume / test / song song được

- Repair loop nằm **trong** một chương, không quyết định thứ tự chương hay stage.
- Checkpoint vẫn chụp ở ranh giới chương, vị trí resume không đổi.
- `batch_parallel_dispatch` vẫn song song theo chương như hiện tại.
- Test: mock `plan_repair` trả `RepairPlan` cố định thì executor và coordinator
  test được tất định. Chỉ planner là nondeterministic, và nó có contract JSON hẹp
  (`strategy` thuộc 3 giá trị) nên validate được.

---

## 4. Config

Thêm vào `PipelineConfig` trong `config/defaults.py` (**không** dùng
`getattr(config, "x", default)` — theo CLAUDE.md, default sống ở một chỗ):

```python
# Agentic repair loop — gộp 5 rewrite pass post-write thành 1 vòng có ngân sách.
# Xem docs/agentic-repair-loop-spec.md.
enable_agentic_repair: bool = True         # mặc định; legacy vẫn là fallback
repair_max_rounds: int = 2                 # tối đa 2 vòng plan -> rewrite -> verify
repair_budget_calls: int = 4               # trần cứng LLM call cho repair mỗi chương
repair_regression_tolerance: float = 0.0   # điểm xấu đi quá mức này -> rollback
repair_fallback_to_legacy: bool = True     # hết budget mà còn lỗi -> chạy pass cũ
repair_planner_model_tier: str = "cheap"   # planner chỉ trả JSON ngắn
repair_min_severity: str = "major"         # dưới mức này không kích hoạt repair
```

`enable_agentic_repair=True` **thay thế** pass 2-5. Pass 1 (self-critique) giữ
nguyên vị trí, findings của nó được nạp vào collector thay vì rewrite ngay.
`False` cho hành vi cũ, không đổi một byte.

**Mặc định `True` (CEO quyết, 2026-08-26)** — sớm hơn cổng K-D mà spec này đặt ra.
Đánh đổi được chấp nhận có ý thức: đường repair có rollback, có fallback về legacy,
và mọi đường lỗi đều non-fatal, nên rủi ro tệ nhất là chất lượng kém đi chứ không
phải hỏng pipeline. Nhưng vì bật mặc định, **smoke run thật trở thành điều kiện
bắt buộc trước khi merge**, không còn là việc nên làm: prompt hợp nhất tới lúc đó
mới chỉ được kiểm bằng LLM giả.

Thêm env override trong `config/persistence.py` theo mẫu dòng 27:
`"STORYFORGE_AGENTIC_REPAIR": ("pipeline", "enable_agentic_repair")`.

---

## 5. Điểm tích hợp

| File | Thay đổi |
| --- | --- |
| `pipeline/layer1_story/chapter_finalizer.py:97-127` | rẽ nhánh: `enable_agentic_repair` -> `repair_chapter(...)`, ngược lại chạy 4 lời gọi cũ nguyên vẹn |
| `pipeline/layer1_story/chapter_rewrites.py` | giữ nguyên hàm; tách phần *detect* sang `repair/collector.py` để gọi lại được mà không side-effect |
| `pipeline/layer1_story/chapter_length_gate.py` | ràng buộc độ dài xuất ra dạng `RepairFinding.hard_constraint`; không rewrite riêng khi repair bật |
| `pipeline/layer1_story/chapter_payoff_rewrite.py` | như trên |
| `pipeline/layer1_story/batch_generator.py:457` | findings từ self-critique nạp vào collector |
| `config/defaults.py` | 7 field ở mục 4 |
| `config/persistence.py` | env override |

Trước khi sửa bất kỳ hàm nào ở trên: chạy `find_referencing_symbols` (Serena) để
lấy danh sách callsite. `finalize_chapter` được gọi từ **3 đường** (sync executor,
async gather, serial fallback) — docstring `chapter_finalizer.py:52-56` xác nhận,
và chính lý do module này tồn tại là để 3 đường không lệch nhau. Vì vậy nhánh
`enable_agentic_repair` phải đặt **bên trong** `finalize_chapter`, không ở callsite.

---

## 6. Observability

Ghi vào trace hiện có (`services/trace_context`) mỗi chương:

```
repair.rounds_used       int
repair.calls_used        int
repair.findings_before   int
repair.findings_after    int
repair.rolled_back       bool
repair.fallback_used     bool
repair.strategy          str
```

SSE log giữ đúng format tiếng Việt hiện tại để FE không phải đổi:
`Ch{n}: sửa {k} lỗi trong 1 lượt viết lại…`

Đây là dữ liệu để so A/B: `calls_used` phải giảm rõ so với nhánh legacy, còn
`findings_after` không được tăng.

---

## 7. Test plan

Theo quy tắc programme: mỗi hạng mục có regression test **fail trước khi fix**.

| Test | Khẳng định | Fail trên code hiện tại |
| --- | --- | --- |
| `test_repair_budget_hard_cap` | vượt `repair_budget_calls` -> thoát, không gọi thêm | có |
| `test_repair_rollback_on_regression` | findings tăng sau rewrite -> content về baseline | có (pass 2-5 không rollback) |
| `test_repair_constraints_merged` | prompt rewrite chứa **mọi** `hard_constraint` | có |
| `test_length_survives_payoff_fix` | chương 1800 từ + payoff thiếu -> sau repair vẫn >= `length_gate_min_ratio × target` **và** payoff đã trả | **có — đây là bug (b), reproduce được ngay hôm nay** |
| `test_repair_disabled_is_byte_identical` | `enable_agentic_repair=False` -> gọi đúng 4 hàm cũ, đúng thứ tự | không (bảo vệ regression) |
| `test_collector_is_pure` | `collect_findings` không mutate `story_context` | có |
| `test_planner_json_contract` | `strategy` ngoài 3 giá trị -> coi như `skip`, không crash | có |
| `test_repair_exception_non_fatal` | planner raise -> chương giữ nguyên, pipeline chạy tiếp | có |

Chạy qua `scripts/run_gate_chunks.ps1` với `STORYFORGE_DISABLE_REAL_EMBEDDINGS=1`
(pytest full-suite một process crash native trên host này).

---

## 8. Lộ trình

**Phase A — hạ tầng, không đổi hành vi.**
Tách detect khỏi commit-warning; dựng `RepairFinding` + `collector`;
`test_collector_is_pure` xanh. Flag vẫn OFF. Rủi ro thấp nhất.

**Phase B — coordinator + executor, planner giả lập.**
`plan_repair` trả plan tất định: gộp mọi finding, `strategy` luôn `full_rewrite`.
Đã đủ để đóng bug (b) và cắt 5 call xuống 1. Bật flag trên một truyện thử.
*Phần lớn giá trị nằm ở đây, và nó chưa cần thêm LLM call nào.*

**Phase C — planner thật.**
Thay planner giả bằng 1 LLM call chọn `targeted` / `full_rewrite` / `skip`.
A/B trên 10 chương: so `calls_used`, `findings_after`, và điểm critique cuối.

**Phase D — quyết định default.**
Bật mặc định chỉ khi Phase C cho thấy call giảm >= 40% mà `findings_after` không
tăng. Nếu không đạt, giữ Phase B (vốn đã có lãi) và bỏ planner.

---

## 9. Rủi ro

| Rủi ro | Giảm thiểu |
| --- | --- |
| Tách detect khỏi side-effect chạm nhiều chỗ hơn dự kiến | Phase A độc lập, flag OFF, gate phải xanh trước khi sang B |
| Một rewrite hợp nhất phải giữ quá nhiều ràng buộc -> model bỏ sót | verify bắt được và rollback; `repair_max_rounds=2` cho một lần thử lại |
| Planner (Phase C) thành overhead thuần | Phase D có tiêu chí bỏ planner rõ ràng; Phase B đứng một mình được |
| 3 đường gọi `finalize_chapter` lệch nhau | rẽ nhánh đặt bên trong `finalize_chapter`, không ở callsite |

---

## 10. Câu hỏi mở

### 10.1 (ĐÃ CHỐT) `chapter_critique_rollback`

Tắt khi `enable_agentic_repair=True`. Lý do: nó tốn 1 call để LLM tự chấm lại
bài của chính nó — đúng loại tín hiệu mục 1.3(1) cho thấy không đáng tin. Repair
loop đã có verify bằng detector tất định, mạnh hơn và rẻ hơn. Giữ nguyên
`chapter_critique_rollback=True` trên nhánh legacy (`enable_agentic_repair=False`)
vì ở đó nó là bảo vệ duy nhất.

### 10.2 Còn mở
1. `repair_planner_model_tier="cheap"` — cần xác nhận tier cheap đang cấu hình
   không phải thinking model.
2. Có đưa L2 `pipeline/layer2_enhance/contract_gate.py` vào cùng khung này ở
   sprint sau không? Nó có hình dạng detect -> rewrite giống hệt.
