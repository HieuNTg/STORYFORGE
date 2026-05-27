/**
 * Tests for sniffers.ts.
 *
 * Mirrors the legacy `web/js/stores/__tests__/sse-sniffers.test.ts` cases.
 * If the backend rewords a log line, the failing test pinpoints exactly
 * which sniffer needs updating before the UI breaks silently.
 */

import { describe, it, expect } from "vitest";
import {
  sniffChapterCompletion,
  sniffAgentTurn,
  sniffAgentScore,
  sniffAgentsPhase,
  sniffAuthorAction,
  sniffDebateMarker,
  sniffL2Agent,
  sniffReaderTurn,
  sniffStateRegistryTick,
  sniffParallelBatch,
} from "./sniffers";

describe("sniffChapterCompletion", () => {
  it("parses ✅ prefixed Vietnamese chapter line", () => {
    expect(sniffChapterCompletion("✅ Chương 3: Đại Đạo Triều Thiên")).toBe(
      "Ch. 3 — Đại Đạo Triều Thiên"
    );
  });

  it("parses Vietnamese chapter line without check mark", () => {
    expect(sniffChapterCompletion("Chương 12: Kết thúc")).toBe(
      "Ch. 12 — Kết thúc"
    );
  });

  it("parses English fallback chapter line", () => {
    expect(sniffChapterCompletion("Chapter 1: Beginning")).toBe(
      "Ch. 1 — Beginning"
    );
  });

  it("tolerates [L1] layer prefix from orchestrator wrapper", () => {
    expect(sniffChapterCompletion("[L1] ✅ Chương 3: Đại Đạo")).toBe(
      "Ch. 3 — Đại Đạo"
    );
  });

  it("collapses internal whitespace in the title", () => {
    expect(sniffChapterCompletion("Chương 5:    Title   With    Spaces  ")).toBe(
      "Ch. 5 — Title With Spaces"
    );
  });

  it("returns null for layer markers", () => {
    expect(sniffChapterCompletion("Layer 2 starting")).toBeNull();
  });

  it("returns null for arbitrary log lines", () => {
    expect(sniffChapterCompletion("arbitrary log")).toBeNull();
  });

  it("returns null for [Agent …] lines", () => {
    expect(sniffChapterCompletion("[Agent 1/6] Sage: argue")).toBeNull();
  });
});

describe("sniffAgentTurn", () => {
  it("parses canonical simulator.py:633 form", () => {
    expect(sniffAgentTurn("[Agent 3/6] Sage: argue")).toEqual({
      idx: 3,
      total: 6,
      name: "Sage",
      action: "argue",
    });
  });

  it("tolerates [L2] layer prefix from orchestrator_layers.py wrapper", () => {
    expect(sniffAgentTurn("[L2] [Agent 3/6] Sage: argue")).toEqual({
      idx: 3,
      total: 6,
      name: "Sage",
      action: "argue",
    });
  });

  it("parses skip action", () => {
    expect(sniffAgentTurn("[Agent 1/4] Cynic: skip")).toEqual({
      idx: 1,
      total: 4,
      name: "Cynic",
      action: "skip",
    });
  });

  it("parses multi-word action and trimmed name", () => {
    expect(sniffAgentTurn("[Agent 2/3]  Devil  Advocate :  raise objection")).toEqual({
      idx: 2,
      total: 3,
      name: "Devil  Advocate",
      action: "raise objection",
    });
  });

  it("returns null when prefix is wrong", () => {
    expect(sniffAgentTurn("[AGENTS] Layer 1 được duyệt!")).toBeNull();
    expect(sniffAgentTurn("Agent 3/6 Sage: argue")).toBeNull();
    expect(sniffAgentTurn("[Agent] Sage: argue")).toBeNull();
  });
});

describe("sniffAgentsPhase", () => {
  it("parses approved-layer marker", () => {
    expect(sniffAgentsPhase("[AGENTS] Layer 1 được duyệt!")).toEqual({
      phase: "approved",
      layer: 1,
    });
    expect(sniffAgentsPhase("[AGENTS] Layer 2 được duyệt!")).toEqual({
      phase: "approved",
      layer: 2,
    });
  });

  it("parses revision marker", () => {
    expect(sniffAgentsPhase("[AGENTS] Cần chỉnh sửa, vòng tiếp theo...")).toEqual({
      phase: "revision",
    });
  });

  it("parses evaluating-layer marker", () => {
    expect(sniffAgentsPhase("[AGENTS] Phòng ban đang đánh giá Layer 1...")).toEqual({
      phase: "evaluating",
      layer: 1,
    });
  });

  it("parses round marker", () => {
    expect(sniffAgentsPhase("[AGENTS] Vòng đánh giá 2/3 - Layer 1")).toEqual({
      phase: "round",
      round: 2,
      totalRounds: 3,
      layer: 1,
    });
  });

  it("tolerates [L2] layer prefix from orchestrator wrapper", () => {
    expect(sniffAgentsPhase("[L2] [AGENTS] Layer 2 được duyệt!")).toEqual({
      phase: "approved",
      layer: 2,
    });
    expect(
      sniffAgentsPhase("[L1] [AGENTS] Cần chỉnh sửa, vòng tiếp theo...")
    ).toEqual({ phase: "revision" });
  });

  it("returns null for unrelated [AGENTS] prose", () => {
    expect(sniffAgentsPhase("[AGENTS] doing something else")).toBeNull();
  });

  it("returns null for non-[AGENTS] lines", () => {
    expect(sniffAgentsPhase("Chương 1: Khởi đầu")).toBeNull();
  });
});

describe("sniffAgentScore", () => {
  it("parses OK agent score line", () => {
    expect(sniffAgentScore("[AGENTS] OK Biên kịch: 0.85/1.0 (2 vấn đề)")).toEqual({
      name: "Biên kịch",
      status: "OK",
      score: 0.85,
      issues: 2,
    });
  });

  it("parses WARN agent score with [L1] prefix", () => {
    expect(sniffAgentScore("[L1] [AGENTS] WARN Đạo diễn: 0.4/1.0 (5 vấn đề)")).toEqual({
      name: "Đạo diễn",
      status: "WARN",
      score: 0.4,
      issues: 5,
    });
  });

  it("returns null for empty string", () => {
    expect(sniffAgentScore("")).toBeNull();
  });

  it("returns null for unrelated log lines", () => {
    expect(sniffAgentScore("[AGENTS] Layer 1 được duyệt!")).toBeNull();
    expect(sniffAgentScore("Chương 1: Khởi đầu")).toBeNull();
  });

  it("returns null when score is missing", () => {
    expect(sniffAgentScore("[AGENTS] OK Biên kịch: (2 vấn đề)")).toBeNull();
  });
});

describe("sniffDebateMarker", () => {
  it("returns the trailing message for [DEBATE] lines", () => {
    expect(sniffDebateMarker("[DEBATE] Round 2 token budget would be exceeded")).toBe(
      "Round 2 token budget would be exceeded"
    );
  });

  it("returns null for non-[DEBATE] lines", () => {
    expect(sniffDebateMarker("[AGENTS] anything")).toBeNull();
    expect(sniffDebateMarker("arbitrary")).toBeNull();
  });

  it("tolerates [L2] layer prefix from orchestrator wrapper", () => {
    expect(
      sniffDebateMarker("[L2] [DEBATE] Round 2 token budget would be exceeded")
    ).toBe("Round 2 token budget would be exceeded");
  });
});

describe("sniffReaderTurn", () => {
  it("parses reader_simulator.py:94 form", () => {
    expect(sniffReaderTurn("[Reader] Simulating chapter 4...")).toEqual({
      chapter: 4,
    });
  });

  it("returns null for non-Reader prefixes", () => {
    expect(sniffReaderTurn("[Agent 1/6] Sage: argue")).toBeNull();
  });

  it("tolerates [L1] layer prefix from orchestrator wrapper", () => {
    expect(sniffReaderTurn("[L1] [Reader] Simulating chapter 4...")).toEqual({
      chapter: 4,
    });
  });
});

describe("sniffStateRegistryTick", () => {
  it("parses character_state_registry.py:135 form", () => {
    expect(sniffStateRegistryTick("[StateRegistry] Extracted states for ch7")).toEqual({
      chapter: 7,
    });
  });

  it("returns null for setting-graph lookalike", () => {
    expect(sniffStateRegistryTick("[SettingGraph] Processed ch7")).toBeNull();
  });

  it("tolerates [L1] layer prefix from orchestrator wrapper", () => {
    expect(
      sniffStateRegistryTick("[L1] [StateRegistry] Extracted states for ch7")
    ).toEqual({ chapter: 7 });
  });
});

describe("sniffParallelBatch", () => {
  it("parses batch_generator.py:1292 form", () => {
    expect(sniffParallelBatch("[ASYNC] Đang viết 5 chương song song...")).toEqual({
      batchSize: 5,
    });
  });

  it("returns null for non-ASYNC prefixes", () => {
    expect(sniffParallelBatch("[Reader] Simulating chapter 1...")).toBeNull();
  });

  it("tolerates [L1] layer prefix from orchestrator wrapper", () => {
    expect(
      sniffParallelBatch("[L1] [ASYNC] Đang viết 5 chương song song...")
    ).toEqual({ batchSize: 5 });
  });
});

describe("sniffAuthorAction (Vietnamese mid-flight form)", () => {
  it("parses '[L1] Đang viết chương N: title' into Nhà văn bubble", () => {
    expect(sniffAuthorAction("[L1] Đang viết chương 3: Hồi Tâm")).toEqual({
      name: "Nhà văn",
      role: "Layer 1",
      action: "Đang viết Chương 3: Hồi Tâm",
    });
  });

  it("trims trailing ellipsis from the title", () => {
    expect(sniffAuthorAction("[L1] Đang viết chương 12: Bước Ngoặt...")).toEqual({
      name: "Nhà văn",
      role: "Layer 1",
      action: "Đang viết Chương 12: Bước Ngoặt",
    });
  });

  it("is case-insensitive on the 'Chương' keyword", () => {
    expect(sniffAuthorAction("[L1] Đang viết Chương 5: Đêm Trăng")).toEqual({
      name: "Nhà văn",
      role: "Layer 1",
      action: "Đang viết Chương 5: Đêm Trăng",
    });
  });

  it("does NOT false-match [QUALITY] lines wrapped with [L1] prefix", () => {
    expect(sniffAuthorAction("[L1] [QUALITY] overall=0.8")).toBeNull();
  });

  it("matches ANY layer prefix via LAYER_PREFIX (sniffer is layer-agnostic)", () => {
    // Grounded on sniffers.ts:15 — LAYER_PREFIX = /(?:\[L\d+\]\s+)?/ allows
    // any [L\d+] wrapper, so an [L2]-prefixed Vietnamese write line still
    // produces the Nhà văn bubble. This is intentional: orchestrator_layers
    // wraps with whichever layer is active, and the bubble UI shows the role
    // string from the parsed result. Caller should rely on detectPhaseFromLog
    // (not this sniffer) for L1-vs-L2 routing.
    expect(sniffAuthorAction("[L2] Đang viết chương 1: X")).toEqual({
      name: "Nhà văn",
      role: "Layer 1",
      action: "Đang viết Chương 1: X",
    });
  });
});

describe("sniffL2Agent", () => {
  it("parses canonical [L2] [Agent X/Y] form from simulator.py:623", () => {
    expect(sniffL2Agent("[L2] [Agent 3/8] Sage: argue")).toEqual({
      current: 3,
      total: 8,
    });
  });

  it("parses first-agent boundary [L2] [Agent 1/N]", () => {
    expect(sniffL2Agent("[L2] [Agent 1/6] Cynic: skip")).toEqual({
      current: 1,
      total: 6,
    });
  });

  it("parses last-agent boundary [L2] [Agent N/N]", () => {
    expect(sniffL2Agent("[L2] [Agent 8/8] Devil Advocate: raise objection")).toEqual({
      current: 8,
      total: 8,
    });
  });

  it("returns null for bare [Agent X/Y] without [L2] prefix (avoids phase pollution from [AGENTS] panel)", () => {
    // sniffAgentTurn still parses this for the agent bubble — but phase-2
    // progress must be driven only by L2-prefixed lines so the L1 agent
    // review panel (which also emits [Agent X/Y]) does not advance phase 2.
    expect(sniffL2Agent("[Agent 3/6] Sage: argue")).toBeNull();
  });

  it("returns null for [L1]-prefixed agent lines", () => {
    expect(sniffL2Agent("[L1] [Agent 2/4] Sage: argue")).toBeNull();
  });

  it("returns null for [L2] [AGENTS] phase markers", () => {
    expect(sniffL2Agent("[L2] [AGENTS] Layer 2 được duyệt!")).toBeNull();
  });

  it("returns null for arbitrary [L2] log lines", () => {
    expect(sniffL2Agent("[L2] Đang phân tích cấu trúc truyện...")).toBeNull();
  });

  it("returns null for empty string", () => {
    expect(sniffL2Agent("")).toBeNull();
  });

  it("returns null when total is zero (defensive against malformed log)", () => {
    expect(sniffL2Agent("[L2] [Agent 0/0] x: y")).toBeNull();
  });
});
