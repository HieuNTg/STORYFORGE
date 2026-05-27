"use client";

/**
 * pipeline-store — high-level pipeline status (phase, errors, session).
 *
 * Owns the linear-progress state shown by PhaseTimeline + the session id used
 * to open SSE streams. Theater-level state (agents, characters, debate) lives
 * in `theater-store`. Per phase-01 spec §Architecture.
 */

import { create } from "zustand";

export type PipelineStatus =
  | "idle"
  | "running"
  | "done"
  | "error"
  | "interrupted";

export type PhaseStatus = "pending" | "active" | "done" | "error";

export interface PhaseEntry {
  label: string;
  status: PhaseStatus;
}

export interface PipelineState {
  status: PipelineStatus;
  sessionId: string | null;
  /** 0-indexed phase number currently active (or last reached). */
  currentPhase: number;
  errors: string[];
  phases: PhaseEntry[];

  start(sessionId: string | null): void;
  setStatus(status: PipelineStatus): void;
  setCurrentPhase(idx: number): void;
  pushError(msg: string): void;
  setSessionId(id: string | null): void;
  reset(): void;
}

const DEFAULT_PHASES: PhaseEntry[] = [
  { label: "Outline", status: "pending" },
  { label: "Layer 1", status: "pending" },
  { label: "Layer 2", status: "pending" },
  { label: "Hoàn tất", status: "pending" },
];

function clonePhases(): PhaseEntry[] {
  return DEFAULT_PHASES.map((p) => ({ ...p }));
}

function applyPhaseProgress(
  prev: PhaseEntry[],
  current: number,
  status: PipelineStatus
): PhaseEntry[] {
  return prev.map((phase, idx) => {
    if (status === "error" && idx === current) return { ...phase, status: "error" };
    if (idx < current) return { ...phase, status: "done" };
    if (idx === current) {
      return { ...phase, status: status === "done" ? "done" : "active" };
    }
    return { ...phase, status: "pending" };
  });
}

export const usePipelineStore = create<PipelineState>((set) => ({
  status: "idle",
  sessionId: null,
  currentPhase: 0,
  errors: [],
  phases: clonePhases(),

  start(sessionId) {
    set({
      status: "running",
      sessionId,
      currentPhase: 0,
      errors: [],
      phases: applyPhaseProgress(clonePhases(), 0, "running"),
    });
  },

  setStatus(status) {
    set((state) => ({
      status,
      phases: applyPhaseProgress(state.phases, state.currentPhase, status),
    }));
  },

  setCurrentPhase(idx) {
    set((state) => {
      const clamped = Math.max(0, Math.min(state.phases.length - 1, idx));
      return {
        currentPhase: clamped,
        phases: applyPhaseProgress(state.phases, clamped, state.status),
      };
    });
  },

  pushError(msg) {
    set((state) => ({ errors: state.errors.concat(msg).slice(-50) }));
  },

  setSessionId(id) {
    set({ sessionId: id });
  },

  reset() {
    set({
      status: "idle",
      sessionId: null,
      currentPhase: 0,
      errors: [],
      phases: clonePhases(),
    });
  },
}));

/** Map free-form log phrasing → phase index. Mirrors `_detectLayer` from web/js/stores/pipeline.ts.
 *
 * Outline vs Layer-1 disambiguation: orchestrator_layers wraps every L1
 * substep with `[L1] `, including the outline-building stage which has no
 * chapter number yet. We treat `[L1]` lines as phase 0 (outline) UNTIL we see
 * an explicit chapter token like "Chương 3" — that's our signal the
 * chapter-writing substep has begun and the stepper can advance to phase 1.
 */
export function detectPhaseFromLog(msg: string, fallback: number): number {
  const up = msg.toUpperCase();
  if (up.includes("[OUTLINE]")) return 0;
  if (up.startsWith("[L2]")) return 2;
  if (up.startsWith("[L1]") || up.startsWith("[L1-")) {
    if (/CHƯƠNG\s+\d+|CHAPTER\s+\d+/.test(up)) return 1;
    // No chapter token yet → still in the outline substep of L1.
    return Math.max(fallback, 0);
  }
  if (up.includes("MEDIA") || up.includes("IMAGE")) return 3;
  if (up.includes("LAYER 2") || up.includes("MÔ PHỎNG") || up.includes("ENHANCE")) return 2;
  if (/CHƯƠNG\s+\d+|CHAPTER\s+\d+/.test(up)) return 1;
  if (up.includes("LAYER 1") || up.includes("TẠO TRUYỆN")) {
    return Math.max(fallback, 0);
  }
  return fallback;
}
