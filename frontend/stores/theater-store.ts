"use client";

/**
 * theater-store — derived presenter state populated from SSE `log` events.
 *
 * Mirrors the legacy `web/js/stores/theater.ts` field shape but ported to
 * Zustand. Arrays are capped at MAX_ENTRIES (R1.3 mitigation) and deduped by
 * id to keep memory bounded across long generations.
 */

import { create } from "zustand";
import {
  sniffAgentTurn,
  sniffAgentScore,
  sniffAgentsPhase,
  sniffAuthorAction,
  sniffChapterParts,
  sniffDebateMarker,
  sniffL2Agent,
  sniffOutlineMarker,
  sniffQualityScore,
  sniffReaderTurn,
  sniffStateRegistryTick,
  type AgentTurn,
  type QualityScoreLine,
} from "@/lib/sse/sniffers";

export type AgentStatus = "thinking" | "speaking" | "done" | "error";

export interface TheaterAgent {
  id: string;
  name: string;
  role?: string;
  status: AgentStatus;
  message: string;
  turn?: number;
  /** Streaming partial text appended from `stream` frames. */
  partial?: string;
}

export interface QualityDimension {
  name: string;
  value: number;
}

export interface QualitySnapshot {
  value: number;
  dimensions: QualityDimension[];
  /** Highest layer index seen so far (1, 2, ...). */
  layer?: number;
  /** Epoch ms when last updated; drives "vừa cập nhật" caption. */
  updatedAt?: number;
}

/**
 * Per-phase sub-progress shown beneath the stepper label.
 * `index` is the 0-based phase index from `pipeline-store`.
 */
export interface PhaseStats {
  /** Optional explicit substring like "đang viết chương 4/12". */
  subLabel?: string;
  /** Optional numeric progress for a tiny progress bar. */
  current?: number;
  /** Total used to compute progress percentage. */
  total?: number;
  /** Frozen summary shown after the phase completes. */
  doneSummary?: string;
}

export interface PartialChapter {
  /** Chapter number when known; falls back to a synthetic id. */
  id: string;
  number: number | null;
  title: string;
  wordCount: number | null;
  /** Epoch ms appended (drives "vừa xong" caption). */
  appendedAt: number;
}

export interface TheaterCharacter {
  id: string;
  name: string;
  personality?: string;
}

export interface TheaterRelationship {
  id: string;
  from: string;
  to: string;
  kind?: string;
}

export interface TheaterState {
  agents: TheaterAgent[];
  quality: QualitySnapshot;
  characters: TheaterCharacter[];
  relationships: TheaterRelationship[];
  readerTurn: number | null;
  debateMarker: string | null;
  graphTick: number;
  /** Live partial chapters seen mid-flight (prepended). */
  partialChapters: PartialChapter[];
  /** Per-phase substep progress keyed by phase index. */
  phaseStats: Record<number, PhaseStats>;

  reset(): void;
  applyLog(msg: string): void;
  applyStream(text: string): void;
  applyDone(payload: TheaterDonePayload): void;
  setQuality(snapshot: QualitySnapshot): void;
}

export interface TheaterDoneQualityItem {
  // Legacy shape (kept for back-compat with older fixtures + custom callers).
  name?: string;
  value?: number;
  // Current backend shape from pipeline_output_builder.build_output_summary.
  layer?: number;
  overall?: number;
  coherence?: number;
  character?: number;
  drama?: number;
  writing?: number;
}

export interface TheaterDonePayload {
  data?: {
    draft?: {
      characters?: Array<{ name?: string; personality?: string }>;
    };
    quality?: TheaterDoneQualityItem[];
    quality_score?: number;
  };
}

const QUALITY_DIM_LABELS: Record<string, string> = {
  coherence: "Mạch lạc",
  character: "Nhân vật",
  drama: "Kịch tính",
  writing: "Văn phong",
};

function buildDimensionsFromBackend(q: TheaterDoneQualityItem): QualityDimension[] {
  const dims: QualityDimension[] = [];
  for (const key of ["coherence", "character", "drama", "writing"] as const) {
    const v = q[key];
    if (Number.isFinite(v)) {
      dims.push({ name: QUALITY_DIM_LABELS[key], value: clamp01(v) });
    }
  }
  return dims;
}

const MAX_ENTRIES = 200;
const MAX_AGENT_BUBBLES = 6;
/** Hard cap for partial stream buffer — keeps long prose from bloating the bubble. */
const STREAM_BUFFER_CHARS = 600;

function lastActiveAgentIndex(agents: TheaterAgent[]): number {
  for (let i = agents.length - 1; i >= 0; i--) {
    const s = agents[i]!.status;
    if (s === "speaking" || s === "thinking") return i;
  }
  return -1;
}

function applyQualityFromLog(
  set: (
    fn:
      | Partial<TheaterState>
      | ((s: TheaterState) => Partial<TheaterState>),
  ) => void,
  q: QualityScoreLine,
): void {
  const dims: QualityDimension[] = [];
  if (Number.isFinite(q.coherence))
    dims.push({ name: QUALITY_DIM_LABELS.coherence, value: clamp01(q.coherence) });
  if (Number.isFinite(q.character))
    dims.push({ name: QUALITY_DIM_LABELS.character, value: clamp01(q.character) });
  if (Number.isFinite(q.drama))
    dims.push({ name: QUALITY_DIM_LABELS.drama, value: clamp01(q.drama) });
  if (Number.isFinite(q.writing))
    dims.push({ name: QUALITY_DIM_LABELS.writing, value: clamp01(q.writing) });
  set({
    quality: {
      value: clamp01(q.overall),
      dimensions: dims,
      layer: q.layer,
      updatedAt: Date.now(),
    },
  });
}

function clamp01(x: unknown): number {
  const n = typeof x === "number" ? x : Number(x);
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function bubbleId(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "agent";
}

function inferStatus(turn: AgentTurn): AgentStatus {
  const action = turn.action.toLowerCase();
  if (action.includes("skip") || action.includes("pass") || action.includes("done")) return "done";
  if (action.includes("think") || action.includes("reflect")) return "thinking";
  return "speaking";
}

function dedupePush<T extends { id: string }>(prev: T[], next: T, cap: number): T[] {
  const idx = prev.findIndex((p) => p.id === next.id);
  if (idx >= 0) {
    const copy = prev.slice();
    copy[idx] = next;
    return copy;
  }
  const appended = prev.concat(next);
  if (appended.length > cap) return appended.slice(appended.length - cap);
  return appended;
}

export const useTheaterStore = create<TheaterState>((set) => ({
  agents: [],
  quality: { value: 0, dimensions: [] },
  characters: [],
  relationships: [],
  readerTurn: null,
  debateMarker: null,
  graphTick: 0,
  partialChapters: [],
  phaseStats: {},

  reset() {
    set({
      agents: [],
      quality: { value: 0, dimensions: [] },
      characters: [],
      relationships: [],
      readerTurn: null,
      debateMarker: null,
      graphTick: 0,
      partialChapters: [],
      phaseStats: {},
    });
  },

  applyLog(msg) {
    if (typeof msg !== "string" || msg.length === 0) return;

    // [OUTLINE] / [QUALITY] markers populate phase + gauge mid-flight.
    const outline = sniffOutlineMarker(msg);
    if (outline) {
      set((state) => ({
        phaseStats: {
          ...state.phaseStats,
          0: {
            ...state.phaseStats[0],
            subLabel: outline.detail ?? "Đang dựng outline",
          },
        },
      }));
      // fall through — also push an author bubble so the Hội thoại panel isn't empty.
      const agent: TheaterAgent = {
        id: "__outline-author",
        name: "Outline Architect",
        role: "Cấu trúc cốt truyện",
        status: "speaking",
        message: outline.detail ?? "Đang dựng outline...",
      };
      set((state) => ({
        agents: dedupePush(state.agents, agent, MAX_AGENT_BUBBLES),
      }));
      return;
    }

    const quality = sniffQualityScore(msg);
    if (quality) {
      applyQualityFromLog(set, quality);
      return;
    }

    // `[L2] [Agent X/Y] …` drives phase-2 sub-progress for the stepper.
    // Fall through so the existing `sniffAgentTurn` still pushes an agent
    // bubble for this same line — phase progress and bubble are independent.
    const l2Agent = sniffL2Agent(msg);
    if (l2Agent) {
      set((state) => {
        const prev2 = state.phaseStats[2];
        const prevCurrent = prev2?.current ?? 0;
        // Monotonic: don't regress if a later log line repeats an earlier idx
        // (e.g. a retry log line). Always trust the latest `total` though,
        // since the agent pool size is fixed for the run.
        const current = Math.max(prevCurrent, l2Agent.current);
        return {
          phaseStats: {
            ...state.phaseStats,
            2: {
              ...prev2,
              current,
              total: l2Agent.total,
              subLabel: `Đang chạy agent ${current}/${l2Agent.total}`,
            },
          },
        };
      });
      // intentional fall-through to sniffAgentTurn below
    }

    const author = sniffAuthorAction(msg);
    if (author) {
      const agent: TheaterAgent = {
        id: bubbleId(author.name),
        name: author.name,
        role: author.role,
        status: "speaking",
        message: author.action,
      };
      set((state) => ({
        agents: dedupePush(state.agents, agent, MAX_AGENT_BUBBLES),
      }));
      return;
    }

    // Chapter completion bumps the partialChapters list + phase progress.
    const chapter = sniffChapterParts(msg);
    if (chapter) {
      set((state) => {
        const next: PartialChapter = {
          id: `ch-${chapter.number}`,
          number: chapter.number,
          title: chapter.title,
          wordCount: null,
          appendedAt: Date.now(),
        };
        const idx = state.partialChapters.findIndex((c) => c.id === next.id);
        const partialChapters =
          idx >= 0
            ? state.partialChapters.map((c, i) => (i === idx ? next : c))
            : [next, ...state.partialChapters].slice(0, MAX_ENTRIES);
        // Highest chapter number drives phase-1 progress; total is filled in
        // later by PipelineScreen from the form input.
        const prev1 = state.phaseStats[1];
        const current = Math.max(prev1?.current ?? 0, chapter.number);
        return {
          partialChapters,
          phaseStats: {
            ...state.phaseStats,
            1: {
              ...prev1,
              current,
              subLabel: `Vừa hoàn thành Chương ${chapter.number}: ${chapter.title}`,
            },
          },
        };
      });
      // fall through so any embedded `[Agent N/M]` / `[AUTHOR]` line still parses below.
    }

    const turn = sniffAgentTurn(msg);
    if (turn) {
      const agent: TheaterAgent = {
        id: bubbleId(turn.name),
        name: turn.name,
        status: inferStatus(turn),
        message: `${turn.name}: ${turn.action}`,
        turn: turn.idx,
      };
      set((state) => ({
        agents: dedupePush(state.agents, agent, MAX_AGENT_BUBBLES),
      }));
      return;
    }

    const score = sniffAgentScore(msg);
    if (score) {
      const agent: TheaterAgent = {
        id: bubbleId(score.name),
        name: score.name,
        status: score.status === "OK" ? "done" : "speaking",
        message: `${score.name}: ${score.score}/1.0 (${score.issues} vấn đề)`,
      };
      set((state) => ({
        agents: dedupePush(state.agents, agent, MAX_AGENT_BUBBLES),
      }));
      return;
    }

    const phase = sniffAgentsPhase(msg);
    if (phase) {
      if (phase.phase === "approved" || phase.phase === "revision") {
        set((state) => ({
          agents: state.agents.map((a) => ({ ...a, status: "done" as AgentStatus })),
        }));
      } else if (phase.phase === "evaluating") {
        const placeholder: TheaterAgent = {
          id: `__phase-evaluating-l${phase.layer}`,
          name: `Phòng ban Layer ${phase.layer}`,
          status: "thinking",
          message: `Đang đánh giá Layer ${phase.layer}...`,
        };
        set((state) => ({
          agents: dedupePush(state.agents, placeholder, MAX_AGENT_BUBBLES),
        }));
      } else if (phase.phase === "round") {
        const placeholder: TheaterAgent = {
          id: `__phase-round-l${phase.layer}-${phase.round}`,
          name: `Vòng ${phase.round}/${phase.totalRounds}`,
          status: "thinking",
          message: `Layer ${phase.layer} — vòng ${phase.round}/${phase.totalRounds}`,
        };
        set((state) => ({
          agents: dedupePush(state.agents, placeholder, MAX_AGENT_BUBBLES),
        }));
      } else if (phase.phase === "tier") {
        const placeholder: TheaterAgent = {
          id: `__phase-tier-${phase.tier}`,
          name: `Tier ${phase.tier}/${phase.totalTiers}`,
          status: "thinking",
          message: `Tier ${phase.tier}/${phase.totalTiers} đang chạy...`,
        };
        set((state) => ({
          agents: dedupePush(state.agents, placeholder, MAX_AGENT_BUBBLES),
        }));
      }
      return;
    }

    const debate = sniffDebateMarker(msg);
    if (debate) {
      set({ debateMarker: debate });
      return;
    }

    const reader = sniffReaderTurn(msg);
    if (reader) {
      set({ readerTurn: reader.chapter });
      return;
    }

    const tick = sniffStateRegistryTick(msg);
    if (tick) {
      set((state) => ({ graphTick: state.graphTick + 1 }));
      return;
    }
  },

  applyStream(text) {
    if (typeof text !== "string" || text.length === 0) return;
    set((state) => {
      // Append to the last "speaking" or "thinking" agent's partial buffer.
      // Falls back to a synthetic "author" bubble when no agent is active yet
      // — fills the L1 dead-air gap before any [AUTHOR]/[Agent] marker fires.
      const activeIdx = lastActiveAgentIndex(state.agents);
      if (activeIdx >= 0) {
        const next = state.agents.slice();
        const cur = next[activeIdx]!;
        next[activeIdx] = {
          ...cur,
          partial: ((cur.partial ?? "") + text).slice(-STREAM_BUFFER_CHARS),
        };
        return { agents: next };
      }
      const placeholder: TheaterAgent = {
        id: "__live-author",
        name: "Tác giả",
        role: "Đang viết",
        status: "speaking",
        message: "",
        partial: text.slice(-STREAM_BUFFER_CHARS),
      };
      return { agents: dedupePush(state.agents, placeholder, MAX_AGENT_BUBBLES) };
    });
  },

  applyDone(payload) {
    const draft = payload?.data?.draft;
    if (draft?.characters) {
      const characters: TheaterCharacter[] = [];
      for (const c of draft.characters) {
        if (!c?.name) continue;
        const next: TheaterCharacter = {
          id: bubbleId(c.name),
          name: c.name,
          personality: c.personality,
        };
        const existing = characters.findIndex((x) => x.id === next.id);
        if (existing >= 0) characters[existing] = next;
        else characters.push(next);
        if (characters.length >= MAX_ENTRIES) break;
      }
      set({ characters });
    }

    const qList = payload?.data?.quality;
    if (Array.isArray(qList) && qList.length > 0) {
      // Backend ships per-layer entries; pick the highest layer as canonical.
      const sorted = qList
        .slice()
        .sort((a, b) => (b?.layer ?? 0) - (a?.layer ?? 0));
      const top = sorted[0]!;
      const backendDims = buildDimensionsFromBackend(top);
      const legacyDims: QualityDimension[] = qList
        .filter(
          (q): q is { name: string; value: number } =>
            typeof q?.name === "string" && Number.isFinite(q?.value),
        )
        .map((q) => ({ name: q.name, value: clamp01(q.value) }));
      const dimensions = backendDims.length > 0 ? backendDims : legacyDims;
      const overall = Number.isFinite(top.overall)
        ? clamp01(top.overall)
        : dimensions.length > 0
          ? dimensions.reduce((s, d) => s + d.value, 0) / dimensions.length
          : clamp01(payload?.data?.quality_score);
      set({
        quality: {
          value: overall,
          dimensions,
          layer: top.layer,
          updatedAt: Date.now(),
        },
      });
    } else if (payload?.data && Number.isFinite(payload.data.quality_score)) {
      set({
        quality: {
          value: clamp01(payload.data.quality_score),
          dimensions: [],
          updatedAt: Date.now(),
        },
      });
    }

    set((state) => {
      const prev1 = state.phaseStats[1];
      const prev2 = state.phaseStats[2];
      let nextPhaseStats = state.phaseStats;

      // Freeze phase-1 (chapters) to 100% on done. Phase-1 `current` is driven
      // by the highest chapter number seen in the stream; if a per-chapter log
      // frame was ever lost it would stick below `total` even though the run
      // finished (H6 — client-side defence; the server-side root cause was the
      // dropped-log drain bug fixed in PR-1). Mirror the phase-2 freeze.
      const total1 = prev1?.total;
      if (total1 && total1 > 0) {
        nextPhaseStats = {
          ...nextPhaseStats,
          1: {
            ...prev1,
            current: total1,
            subLabel: undefined,
            doneSummary: `Hoàn tất ${total1} chương`,
          },
        };
      }

      // Freeze phase-2 summary if any L2 agent progress was observed mid-run
      // so the stepper reads "Hoàn tất Y agents" instead of stale "Đang chạy…".
      const total2 = prev2?.total;
      if (total2 && total2 > 0) {
        nextPhaseStats = {
          ...nextPhaseStats,
          2: {
            ...prev2,
            current: total2,
            subLabel: undefined,
            doneSummary: `Hoàn tất ${total2} agents`,
          },
        };
      }

      return {
        agents: state.agents.map((a) => ({ ...a, status: "done" as AgentStatus })),
        phaseStats: nextPhaseStats,
      };
    });
  },

  setQuality(snapshot) {
    set({
      quality: {
        value: clamp01(snapshot.value),
        dimensions: snapshot.dimensions.map((d) => ({
          name: d.name,
          value: clamp01(d.value),
        })),
      },
    });
  },
}));
