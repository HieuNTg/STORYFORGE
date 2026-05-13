/**
 * theater store — Forge UI pipeline-page state.
 *
 * Singleton store registered as `$store.theater`, populated by the
 * pipeline store's SSE event loop (see _emitTheater* in pipeline.ts).
 * Pure presenter state — every field is derived from SSE signals or the
 * final `done` payload. No network calls live here.
 *
 * Consumers:
 *   - AgentBubble × N — bound to `agents[]`
 *   - QualityGauge    — bound to `quality`
 *   - CharacterGraph  — bound to `characters[]` + `relationships[]`
 *   - page wrapper    — `data-state="<pageState>"` drives CSS morphs
 *
 * Lifecycle:
 *   - reset() at the start of every pipeline run
 *   - applyLog(msg, progress) called per SSE `log` event
 *   - applyDone(payload) called once on SSE `done`
 *   - applyError(msg) called on SSE `error` / 'interrupted'
 *
 * The store is registered ONLY when the forge-ui flag is on (see app.ts).
 * When absent, the pipeline-store bridge no-ops silently.
 */

import {
  sniffAgentTurn,
  sniffAgentsPhase,
  sniffReaderTurn,
  sniffDebateMarker,
  sniffStateRegistryTick,
  type AgentTurn,
} from './sse-sniffers';
import {
  deriveNodes as deriveCharacterNodes,
  deriveEdges as deriveCharacterEdges,
} from './character-edges';
import type { CharacterNode, CharacterEdge } from '../components/CharacterGraph';

type PageState = 'idle' | 'generating' | 'done' | 'error' | 'interrupted';

export type AgentState =
  | 'idle'
  | 'thinking'
  | 'speaking'
  | 'debating'
  | 'voting'
  | 'done';

export interface TheaterAgent {
  id: string;
  name: string;
  state: AgentState;
  message: string;
  score: number | null;
}

export interface QualityDimension {
  name: string;
  value: number;
}

export interface TheaterStore {
  pageState: PageState;
  agents: TheaterAgent[];
  quality: { value: number; dimensions: QualityDimension[] };
  characters: CharacterNode[];
  relationships: CharacterEdge[];
  /** Most recent debate-machinery marker, for the live-log mini-strip. */
  lastDebateMarker: string | null;
  /** Most recent chapter currently being reader-simulated. Null when idle. */
  readerChapter: number | null;
  /** Bumps each time the StateRegistry emits an extraction tick — drives a "dirty" pulse on the CharacterGraph. */
  graphTick: number;

  reset(): void;
  setPageState(s: PageState): void;
  applyLog(msg: string, progress: number): void;
  applyDone(payload: TheaterDonePayload): void;
  applyError(msg: string | null): void;
  applyInterrupted(msg: string | null): void;
}

/** Subset of the SSE `done` payload that the theater consumes. */
export interface TheaterDonePayload {
  data?: {
    draft?: {
      characters?: Array<{ name?: string; personality?: string }>;
      chapters?: Array<{ number?: number; content?: string }>;
    };
    quality?: Array<{ name?: string; value?: number }>;
    quality_score?: number;
  };
}

const MAX_AGENT_BUBBLES = 6;

function clamp01(x: unknown): number {
  const n = typeof x === 'number' ? x : Number(x);
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function inferState(turn: AgentTurn): AgentState {
  const action = turn.action.toLowerCase();
  if (action.includes('vote') || action.includes('approve') || action.includes('reject')) return 'voting';
  if (action.includes('argue') || action.includes('counter') || action.includes('debate')) return 'debating';
  if (action.includes('support') || action.includes('agree') || action.includes('speak')) return 'speaking';
  if (action.includes('think') || action.includes('reflect') || action.includes('analyze')) return 'thinking';
  if (action.includes('skip') || action.includes('pass') || action.includes('done')) return 'done';
  return 'speaking';
}

function bubbleId(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '') || 'agent';
}

function pushAgent(prev: TheaterAgent[], turn: AgentTurn): TheaterAgent[] {
  const id = bubbleId(turn.name);
  const state = inferState(turn);
  const message = `${turn.name}: ${turn.action}`;
  const existingIdx = prev.findIndex((a) => a.id === id);
  if (existingIdx >= 0) {
    const next = prev.slice();
    next[existingIdx] = { ...prev[existingIdx]!, state, message };
    return next;
  }
  const appended = prev.concat({ id, name: turn.name, state, message, score: null });
  // Keep the newest N — drop from the head.
  if (appended.length > MAX_AGENT_BUBBLES) return appended.slice(appended.length - MAX_AGENT_BUBBLES);
  return appended;
}

export function createTheaterStore(): TheaterStore {
  return {
    pageState: 'idle',
    agents: [],
    quality: { value: 0, dimensions: [] },
    characters: [],
    relationships: [],
    lastDebateMarker: null,
    readerChapter: null,
    graphTick: 0,

    reset(): void {
      this.pageState = 'generating';
      this.agents = [];
      this.quality = { value: 0, dimensions: [] };
      this.characters = [];
      this.relationships = [];
      this.lastDebateMarker = null;
      this.readerChapter = null;
      this.graphTick = 0;
    },

    setPageState(s: PageState): void {
      this.pageState = s;
    },

    applyLog(msg: string, _progress: number): void {
      if (typeof msg !== 'string' || msg.length === 0) return;

      const turn = sniffAgentTurn(msg);
      if (turn) {
        this.agents = pushAgent(this.agents, turn);
        return;
      }

      const phase = sniffAgentsPhase(msg);
      if (phase) {
        // Mark all current agents as 'voting' on a phase decision.
        this.agents = this.agents.map((a) => ({ ...a, state: 'voting' as AgentState }));
        return;
      }

      const debate = sniffDebateMarker(msg);
      if (debate) {
        this.lastDebateMarker = debate;
        return;
      }

      const reader = sniffReaderTurn(msg);
      if (reader) {
        this.readerChapter = reader.chapter;
        return;
      }

      const tick = sniffStateRegistryTick(msg);
      if (tick) {
        this.graphTick += 1;
        return;
      }
    },

    applyDone(payload: TheaterDonePayload): void {
      this.pageState = 'done';
      const draft = payload?.data?.draft;
      if (draft) {
        this.characters = deriveCharacterNodes(draft);
        this.relationships = deriveCharacterEdges(draft);
      }

      const qList = payload?.data?.quality;
      if (Array.isArray(qList) && qList.length > 0) {
        const dimensions: QualityDimension[] = qList
          .filter((q): q is { name: string; value: number } => typeof q?.name === 'string' && Number.isFinite(q?.value))
          .map((q) => ({ name: q.name, value: clamp01(q.value) }));
        const overall =
          dimensions.length > 0
            ? dimensions.reduce((s, d) => s + d.value, 0) / dimensions.length
            : clamp01(payload?.data?.quality_score);
        this.quality = { value: overall, dimensions };
      } else if (payload?.data && Number.isFinite(payload.data.quality_score)) {
        this.quality = { value: clamp01(payload.data.quality_score), dimensions: [] };
      }

      // Mark all current agents as resolved.
      this.agents = this.agents.map((a) => ({ ...a, state: 'done' as AgentState }));
    },

    applyError(_msg: string | null): void {
      this.pageState = 'error';
    },

    applyInterrupted(_msg: string | null): void {
      this.pageState = 'interrupted';
    },
  };
}
