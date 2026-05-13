/**
 * sse-sniffers.ts — pure-function parsers for SSE `log` event strings.
 *
 * Backend emits live progress as free-form Vietnamese/English strings via
 * `progress_callback(msg)`. There is no structured live event channel.
 * This module is the single point of regex truth for client-side parsing.
 *
 * Contract: every sniffer is pure (string → structured-or-null), has a
 * unit test that pins the canonical backend phrasing, and is safe to call
 * on every `log` event without performance concern (regex is O(n) on a
 * short string).
 *
 * If the backend re-words a log line, the corresponding sniffer test
 * fires first — surface the contract change before the UI breaks silently.
 *
 * Backend prefix catalog (see plans/.../m2-sse-payload-audit.md):
 *   - "✅ Chương N: …"                  → sniffChapterCompletion
 *   - "Chương N: …"                     → sniffChapterCompletion
 *   - "Chapter N: …"                    → sniffChapterCompletion (English fallback)
 *   - "[Agent k/N] <name>: <action>"    → sniffAgentTurn
 *   - "[AGENTS] Layer N được duyệt!"    → sniffAgentsPhase ({phase:'approved', layer})
 *   - "[AGENTS] Cần chỉnh sửa, …"        → sniffAgentsPhase ({phase:'revision'})
 *   - "[DEBATE] …"                      → sniffDebateMarker (loose; freeform message)
 *   - "[Reader] Simulating chapter N…"  → sniffReaderTurn
 *   - "[StateRegistry] Extracted states for chN" → sniffStateRegistryTick
 *   - "[ASYNC] Đang viết N chương song song…" → sniffParallelBatch
 *   - "Layer 1 starting" / "Layer 2 starting" → detectLayer (lives in pipeline store)
 */

/**
 * Parse a chapter-completion log line.
 * Returns "Ch. N — title" or "Ch. N" when title is empty.
 */
export function sniffChapterCompletion(msg: string): string | null {
  const m = msg.match(/^(?:✅\s*)?(?:Chương|Chapter)\s+(\d+):\s*(.+?)\s*$/);
  if (!m) return null;
  const title = (m[2] || '').replace(/\s+/g, ' ').trim();
  return title.length > 0 ? `Ch. ${m[1]} — ${title}` : `Ch. ${m[1]}`;
}

export interface AgentTurn {
  /** 1-indexed agent number within the round. */
  idx: number;
  /** Total agents in the round. */
  total: number;
  /** Agent display name (e.g. "Sage", "Cynic"). */
  name: string;
  /** Action verb the agent took: "argue" | "support" | "skip" | etc. */
  action: string;
}

/**
 * Parse a per-agent debate-turn log line from `simulator.py:633`.
 * Canonical form: `[Agent 3/6] Sage: argue`
 */
export function sniffAgentTurn(msg: string): AgentTurn | null {
  const m = msg.match(/^\[Agent\s+(\d+)\/(\d+)\]\s+([^:]+?):\s+(.+?)\s*$/);
  if (!m) return null;
  return {
    idx: parseInt(m[1]!, 10),
    total: parseInt(m[2]!, 10),
    name: m[3]!.trim(),
    action: m[4]!.trim(),
  };
}

export interface AgentsPhase {
  /** 'approved' when a layer passed agent review; 'revision' when another round is needed. */
  phase: 'approved' | 'revision';
  /** Layer number (1 or 2) when known. */
  layer?: number;
}

/**
 * Parse the `[AGENTS] …` phase markers from `agent_registry.py:237/242`.
 * Two canonical shapes:
 *   - "[AGENTS] Layer 1 được duyệt!"        → approved
 *   - "[AGENTS] Cần chỉnh sửa, vòng tiếp theo..." → revision
 */
export function sniffAgentsPhase(msg: string): AgentsPhase | null {
  const approved = msg.match(/^\[AGENTS\]\s+Layer\s+(\d+)\s+được\s+duyệt/);
  if (approved) {
    return { phase: 'approved', layer: parseInt(approved[1]!, 10) };
  }
  if (/^\[AGENTS\]\s+Cần\s+chỉnh\s+sửa/.test(msg)) {
    return { phase: 'revision' };
  }
  return null;
}

/**
 * Detect any `[DEBATE] …` marker. Returns the trailing message text or null.
 * Used as a low-fidelity "debate machinery active" signal — the body is freeform.
 */
export function sniffDebateMarker(msg: string): string | null {
  const m = msg.match(/^\[DEBATE\]\s+(.+?)\s*$/);
  return m ? m[1]! : null;
}

/**
 * Parse `[Reader] Simulating chapter N…` from `reader_simulator.py:94`.
 * Returns the chapter number under test.
 */
export function sniffReaderTurn(msg: string): { chapter: number } | null {
  const m = msg.match(/^\[Reader\]\s+Simulating\s+chapter\s+(\d+)/);
  return m ? { chapter: parseInt(m[1]!, 10) } : null;
}

/**
 * Parse `[StateRegistry] Extracted states for chN` from
 * `character_state_registry.py:135`. Drives a CharacterGraph dirty-tick.
 */
export function sniffStateRegistryTick(msg: string): { chapter: number } | null {
  const m = msg.match(/^\[StateRegistry\]\s+Extracted\s+states\s+for\s+ch(\d+)/);
  return m ? { chapter: parseInt(m[1]!, 10) } : null;
}

/**
 * Parse `[ASYNC] Đang viết N chương song song…` from
 * `batch_generator.py:1292`. Returns the batch size.
 */
export function sniffParallelBatch(msg: string): { batchSize: number } | null {
  const m = msg.match(/^\[ASYNC\]\s+Đang\s+viết\s+(\d+)\s+chương\s+song\s+song/);
  return m ? { batchSize: parseInt(m[1]!, 10) } : null;
}
