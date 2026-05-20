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
  sniffAgentsPhase,
  sniffDebateMarker,
  sniffReaderTurn,
  sniffStateRegistryTick,
  type AgentTurn,
} from "@/lib/sse/sniffers";

export type AgentStatus = "thinking" | "speaking" | "done" | "error";

export interface TheaterAgent {
  id: string;
  name: string;
  status: AgentStatus;
  message: string;
  turn?: number;
}

export interface QualityDimension {
  name: string;
  value: number;
}

export interface QualitySnapshot {
  value: number;
  dimensions: QualityDimension[];
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

  reset(): void;
  applyLog(msg: string): void;
  applyDone(payload: TheaterDonePayload): void;
  setQuality(snapshot: QualitySnapshot): void;
}

export interface TheaterDonePayload {
  data?: {
    draft?: {
      characters?: Array<{ name?: string; personality?: string }>;
    };
    quality?: Array<{ name?: string; value?: number }>;
    quality_score?: number;
  };
}

const MAX_ENTRIES = 200;
const MAX_AGENT_BUBBLES = 6;

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

  reset() {
    set({
      agents: [],
      quality: { value: 0, dimensions: [] },
      characters: [],
      relationships: [],
      readerTurn: null,
      debateMarker: null,
      graphTick: 0,
    });
  },

  applyLog(msg) {
    if (typeof msg !== "string" || msg.length === 0) return;

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

    const phase = sniffAgentsPhase(msg);
    if (phase) {
      set((state) => ({
        agents: state.agents.map((a) => ({ ...a, status: "done" as AgentStatus })),
      }));
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
      const dimensions: QualityDimension[] = qList
        .filter(
          (q): q is { name: string; value: number } =>
            typeof q?.name === "string" && Number.isFinite(q?.value)
        )
        .map((q) => ({ name: q.name, value: clamp01(q.value) }));
      const overall =
        dimensions.length > 0
          ? dimensions.reduce((s, d) => s + d.value, 0) / dimensions.length
          : clamp01(payload?.data?.quality_score);
      set({ quality: { value: overall, dimensions } });
    } else if (payload?.data && Number.isFinite(payload.data.quality_score)) {
      set({ quality: { value: clamp01(payload.data.quality_score), dimensions: [] } });
    }

    set((state) => ({
      agents: state.agents.map((a) => ({ ...a, status: "done" as AgentStatus })),
    }));
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
