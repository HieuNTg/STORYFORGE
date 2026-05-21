/**
 * sniffers.ts — pure-function parsers for SSE `log` event strings.
 *
 * Ported verbatim from `web/js/stores/sse-sniffers.ts`. The regex source must
 * match the legacy module exactly; the upstream backend log format is the
 * implicit contract. If the backend rewords a line, the corresponding unit
 * test fires first so the failure surfaces before the UI silently breaks.
 *
 * Note on `LAYER_PREFIX`: `orchestrator_layers.py` wraps each subsystem's
 * `progress_callback` with `[L1] ` / `[L2] ` (and any future `[L3] `) so log
 * tail consumers can tell which layer emitted the line. The sniffers must
 * tolerate that optional prefix or the panels silently never populate.
 */

const LAYER_PREFIX = /(?:\[L\d+\]\s+)?/.source;

/**
 * Parse a chapter-completion log line.
 * Returns "Ch. N — title" or "Ch. N" when title is empty.
 */
export function sniffChapterCompletion(msg: string): string | null {
  const m = msg.match(
    new RegExp(`^${LAYER_PREFIX}(?:✅\\s*)?(?:Chương|Chapter)\\s+(\\d+):\\s*(.+?)\\s*$`)
  );
  if (!m) return null;
  const title = (m[2] || "").replace(/\s+/g, " ").trim();
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
  const m = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[Agent\\s+(\\d+)\\/(\\d+)\\]\\s+([^:]+?):\\s+(.+?)\\s*$`)
  );
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
  phase: "approved" | "revision";
  /** Layer number (1 or 2) when known. */
  layer?: number;
}

/**
 * Parse the `[AGENTS] …` phase markers from `agent_registry.py:237/242`.
 */
export function sniffAgentsPhase(msg: string): AgentsPhase | null {
  const approved = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[AGENTS\\]\\s+Layer\\s+(\\d+)\\s+được\\s+duyệt`)
  );
  if (approved) {
    return { phase: "approved", layer: parseInt(approved[1]!, 10) };
  }
  if (new RegExp(`^${LAYER_PREFIX}\\[AGENTS\\]\\s+Cần\\s+chỉnh\\s+sửa`).test(msg)) {
    return { phase: "revision" };
  }
  return null;
}

/**
 * Detect any `[DEBATE] …` marker. Returns the trailing message text or null.
 */
export function sniffDebateMarker(msg: string): string | null {
  const m = msg.match(new RegExp(`^${LAYER_PREFIX}\\[DEBATE\\]\\s+(.+?)\\s*$`));
  return m ? m[1]! : null;
}

/**
 * Parse `[Reader] Simulating chapter N…` from `reader_simulator.py:94`.
 */
export function sniffReaderTurn(msg: string): { chapter: number } | null {
  const m = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[Reader\\]\\s+Simulating\\s+chapter\\s+(\\d+)`)
  );
  return m ? { chapter: parseInt(m[1]!, 10) } : null;
}

/**
 * Parse `[StateRegistry] Extracted states for chN` from
 * `character_state_registry.py:135`.
 */
export function sniffStateRegistryTick(
  msg: string
): { chapter: number } | null {
  const m = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[StateRegistry\\]\\s+Extracted\\s+states\\s+for\\s+ch(\\d+)`)
  );
  return m ? { chapter: parseInt(m[1]!, 10) } : null;
}

/**
 * Parse `[ASYNC] Đang viết N chương song song…` from `batch_generator.py:1292`.
 */
export function sniffParallelBatch(
  msg: string
): { batchSize: number } | null {
  const m = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[ASYNC\\]\\s+Đang\\s+viết\\s+(\\d+)\\s+chương\\s+song\\s+song`)
  );
  return m ? { batchSize: parseInt(m[1]!, 10) } : null;
}
