"use client";

/**
 * simulation-store — Transcript playback + manual/AI turn injection.
 *
 * State:
 *   - logs: TranscriptTurn[]   — full ordered transcript
 *   - cursor: number           — playback index (-1 = before start)
 *   - playing: boolean         — auto-advance on interval
 *   - dramaLevel: DramaLevel   — current intensity (locked unless enable_drama_climax)
 *   - topic: string            — scene topic shown to AI continue
 *   - characters: dict[]       — opaque shapes forwarded to backend
 *   - outcomeSummary: string   — joined drama_suggestions from backend
 *   - sessionId: string | null — backing pipeline session (for hydrate)
 *   - busy: boolean            — true while continueAI() is in flight
 *
 * Persistence: NONE. Transcripts derive from session artifact + ephemeral
 * injections. Persisting raw LLM output would burn localStorage budget for no
 * recall value (CLAUDE.md Rule 11).
 */

import { create } from "zustand";
import {
  continueSimulation,
  getSimulationTranscript,
} from "@/lib/api/simulation";
import type { DramaLevel, TranscriptTurn } from "@/types/story";

export interface SimulationState {
  sessionId: string | null;
  logs: TranscriptTurn[];
  cursor: number;
  playing: boolean;
  dramaLevel: DramaLevel;
  topic: string;
  characters: Array<Record<string, unknown>>;
  outcomeSummary: string;
  busy: boolean;
  error: string | null;

  reset(): void;
  loadFromSession(sessionId: string): Promise<void>;
  setTopic(topic: string): void;
  setDramaLevel(level: DramaLevel): void;
  setCharacters(chars: Array<Record<string, unknown>>): void;
  injectTurn(turn: Omit<TranscriptTurn, "id">): void;
  continueAI(): Promise<void>;
  stepForward(): void;
  stepBackward(): void;
  play(): void;
  pause(): void;
  jumpTo(idx: number): void;
}

const MAX_LOGS = 200;
const HISTORY_TAIL = 6;

function makeTurnId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useSimulationStore = create<SimulationState>((set, get) => ({
  sessionId: null,
  logs: [],
  cursor: -1,
  playing: false,
  dramaLevel: "high",
  topic: "",
  characters: [],
  outcomeSummary: "",
  busy: false,
  error: null,

  reset() {
    set({
      sessionId: null,
      logs: [],
      cursor: -1,
      playing: false,
      topic: "",
      characters: [],
      outcomeSummary: "",
      busy: false,
      error: null,
    });
  },

  async loadFromSession(sessionId) {
    set({ busy: true, error: null });
    try {
      const data = await getSimulationTranscript(sessionId);
      set({
        sessionId,
        logs: data.logs.slice(0, MAX_LOGS),
        outcomeSummary: data.outcomeSummary,
        cursor: data.logs.length > 0 ? 0 : -1,
        busy: false,
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "load failed";
      set({ busy: false, error: msg });
    }
  },

  setTopic(topic) {
    set({ topic: topic.slice(0, 2000) });
  },

  setDramaLevel(level) {
    set({ dramaLevel: level });
  },

  setCharacters(chars) {
    set({ characters: chars.slice(0, 10) });
  },

  injectTurn(turn) {
    const next: TranscriptTurn = {
      id: makeTurnId("t-inj"),
      senderId: turn.senderId,
      senderName: turn.senderName,
      emotion: turn.emotion ?? "",
      actionDetails: turn.actionDetails ?? "",
      speech: turn.speech ?? "",
    };
    set((s) => {
      const appended = s.logs.concat(next);
      const trimmed =
        appended.length > MAX_LOGS ? appended.slice(appended.length - MAX_LOGS) : appended;
      return { logs: trimmed, cursor: trimmed.length - 1 };
    });
  },

  async continueAI() {
    const { topic, characters, dramaLevel, logs, busy } = get();
    if (busy) return;
    if (!topic.trim() || characters.length === 0) {
      set({ error: "topic and characters required" });
      return;
    }
    set({ busy: true, error: null });
    try {
      const turn = await continueSimulation({
        characters,
        historyLogs: logs.slice(-HISTORY_TAIL),
        topic,
        dramaLevel,
      });
      set((s) => {
        const appended = s.logs.concat(turn);
        const trimmed =
          appended.length > MAX_LOGS ? appended.slice(appended.length - MAX_LOGS) : appended;
        return { logs: trimmed, cursor: trimmed.length - 1, busy: false };
      });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "continue failed";
      set({ busy: false, error: msg });
    }
  },

  stepForward() {
    set((s) => ({ cursor: Math.min(s.cursor + 1, s.logs.length - 1) }));
  },

  stepBackward() {
    set((s) => ({ cursor: Math.max(s.cursor - 1, 0) }));
  },

  play() {
    set({ playing: true });
  },

  pause() {
    set({ playing: false });
  },

  jumpTo(idx) {
    set((s) => ({
      cursor: Math.min(Math.max(idx, 0), Math.max(s.logs.length - 1, 0)),
    }));
  },
}));
