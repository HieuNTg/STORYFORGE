/**
 * Tests for `detectPhaseFromLog` — the free-form log → phase index mapper used
 * by PipelineScreen to drive the linear stepper.
 *
 * Critical contract this sprint added (see pipeline-store.ts:122-138):
 *   - `[L1]` without an explicit "Chương N" token must stay on phase 0
 *     (outline substep of Layer-1) so the stepper doesn't jump prematurely.
 *   - `[L1] Chương N` promotes to phase 1.
 *   - Phase is monotonic relative to the `fallback` arg for outline lines.
 */

import { describe, it, expect } from "vitest";
import { detectPhaseFromLog } from "./pipeline-store";

describe("detectPhaseFromLog", () => {
  it("recognises [OUTLINE] markers as phase 0", () => {
    expect(detectPhaseFromLog("[OUTLINE] Đang dựng outline truyện…", 0)).toBe(0);
  });

  it("keeps phase 0 for [L1] outline substep with no chapter token", () => {
    // Grounded on pipeline-store.ts:134-138 — `[L1]` without "Chương N" returns
    // Math.max(fallback, 0). With fallback=0 → 0.
    expect(detectPhaseFromLog("[L1] Đang xây dựng macro arc…", 0)).toBe(0);
  });

  it("does NOT regress phase when fallback is already past outline", () => {
    // Math.max(fallback, 0) = max(1, 0) = 1 → monotonic guarantee.
    expect(detectPhaseFromLog("[L1] Đang xây dựng macro arc…", 1)).toBe(1);
  });

  it("promotes [L1] with explicit Chương N to phase 1", () => {
    expect(detectPhaseFromLog("[L1] Đang viết chương 4: Foo", 0)).toBe(1);
  });

  it("promotes [L1-WRITER] substep with Chương N to phase 1", () => {
    expect(detectPhaseFromLog("[L1-WRITER] Chương 7: Bar", 0)).toBe(1);
  });

  it("recognises [L2] as phase 2 regardless of fallback", () => {
    expect(detectPhaseFromLog("[L2] Agent 3/8", 1)).toBe(2);
  });

  it("[L2] beats earlier [OUTLINE] when called sequentially", () => {
    // Sequential simulation: caller chains fallback from previous return.
    // 1) [OUTLINE] line with fallback=0 → returns 0.
    // 2) [L2] line with fallback=0 (from step 1) → returns 2.
    // Grounded on pipeline-store.ts:133 — `up.startsWith("[L2]")` short-circuits
    // before any later branches, so the [L2] line always wins.
    const after1 = detectPhaseFromLog("[OUTLINE] Đang dựng outline truyện…", 0);
    expect(after1).toBe(0);
    const after2 = detectPhaseFromLog("[L2] anything", after1);
    expect(after2).toBe(2);
  });

  it("does not regress phase for [QUALITY] L1 metric lines", () => {
    // Grounded on pipeline-store.ts:130-145 — "[QUALITY] L1 overall=0.7" has no
    // [OUTLINE]/[L1]/[L2] prefix branch matched (startsWith checks fail because
    // the line starts with "[QUALITY]"), no "LAYER 1"/"LAYER 2" substring
    // (uppercase "L1" ≠ "LAYER 1"), and no "Chương N" token. Therefore the
    // function falls through to `return fallback;`.
    expect(detectPhaseFromLog("[QUALITY] L1 overall=0.7", 1)).toBe(1);
  });

  it("returns fallback for unrecognised log noise", () => {
    expect(detectPhaseFromLog("random log noise", 2)).toBe(2);
  });
});
