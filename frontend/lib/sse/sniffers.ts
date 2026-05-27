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

export type AgentsPhase =
  | { phase: "approved"; layer: number }
  | { phase: "revision" }
  | { phase: "evaluating"; layer: number }
  | { phase: "round"; round: number; totalRounds: number; layer: number }
  | { phase: "tier"; tier: number; totalTiers: number };

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
  const evaluating = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[AGENTS\\]\\s+Phòng\\s+ban\\s+đang\\s+đánh\\s+giá\\s+Layer\\s+(\\d+)`)
  );
  if (evaluating) {
    return { phase: "evaluating", layer: parseInt(evaluating[1]!, 10) };
  }
  const round = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[AGENTS\\]\\s+Vòng\\s+đánh\\s+giá\\s+(\\d+)\\/(\\d+)\\s+-\\s+Layer\\s+(\\d+)`)
  );
  if (round) {
    return {
      phase: "round",
      round: parseInt(round[1]!, 10),
      totalRounds: parseInt(round[2]!, 10),
      layer: parseInt(round[3]!, 10),
    };
  }
  const tier = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[AGENTS\\]\\s+Tier\\s+(\\d+)\\/(\\d+):`)
  );
  if (tier) {
    return {
      phase: "tier",
      tier: parseInt(tier[1]!, 10),
      totalTiers: parseInt(tier[2]!, 10),
    };
  }
  return null;
}

export interface AgentScore {
  name: string;
  status: "OK" | "WARN";
  score: number;
  issues: number;
}

/**
 * Parse `[AGENTS] OK|WARN <name>: <score>/1.0 (<n> vấn đề)` from `agent_registry.py`.
 */
export function sniffAgentScore(msg: string): AgentScore | null {
  const m = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[AGENTS\\]\\s+(OK|WARN)\\s+([^:]+):\\s+([\\d.]+)\\/1\\.0\\s+\\((\\d+)\\s+vấn đề\\)`)
  );
  if (!m) return null;
  return {
    name: m[2]!.trim(),
    status: m[1] as "OK" | "WARN",
    score: parseFloat(m[3]!),
    issues: parseInt(m[4]!, 10),
  };
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

/**
 * Parse the `[L2] [Agent X/Y] …` per-agent progress marker emitted by
 * `pipeline/layer2_enhance/simulator.py:623`:
 *
 *     progress_callback(f"[Agent {idx + 1}/{len(agent_names)}] {name}: …")
 *
 * which is wrapped by `orchestrator_layers.py:976` as `[L2] {m}` before
 * reaching the SSE feed.
 *
 * Returns `{ current, total }` for driving `phaseStats[2]` progress, or null
 * when the line is not an L2 agent turn. We REQUIRE the `[L2]` prefix here
 * (unlike `sniffAgentTurn`, which also accepts bare `[Agent N/M]`) because
 * phase-2 progress must not be polluted by `[AGENTS]` panel rounds during
 * Layer 1 review.
 */
export function sniffL2Agent(
  msg: string,
): { current: number; total: number } | null {
  const m = msg.match(
    /^\[L2\]\s+\[Agent\s+(\d+)\/(\d+)\]/,
  );
  if (!m) return null;
  const current = parseInt(m[1]!, 10);
  const total = parseInt(m[2]!, 10);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
    return null;
  }
  return { current, total };
}

/**
 * Structured chapter-complete parser. Same regex as `sniffChapterCompletion`
 * but returns the parts so `partialChapters` can be keyed by chapter number.
 */
export function sniffChapterParts(
  msg: string,
): { number: number; title: string } | null {
  const m = msg.match(
    new RegExp(`^${LAYER_PREFIX}(?:✅\\s*)?(?:Chương|Chapter)\\s+(\\d+):\\s*(.+?)\\s*$`),
  );
  if (!m) return null;
  const title = (m[2] || "").replace(/\s+/g, " ").trim();
  return { number: parseInt(m[1]!, 10), title };
}

/**
 * Parse `[OUTLINE] …` marker emitted at the start of outline generation
 * from `pipeline/orchestrator_layers.py`. The trailing detail is shown
 * beneath the stepper so phase 0 stops feeling stuck.
 */
export function sniffOutlineMarker(
  msg: string,
): { detail: string | null } | null {
  const m = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[OUTLINE\\]\\s*(.*)$`),
  );
  if (!m) return null;
  const detail = (m[1] || "").trim();
  return { detail: detail.length > 0 ? detail : null };
}

export interface QualityScoreLine {
  layer: number;
  overall: number;
  coherence: number;
  character: number;
  drama: number;
  writing: number;
}

/**
 * Parse `[QUALITY] L1 overall=0.72 coherence=0.8 character=0.7 drama=0.65 writing=0.81`
 * emitted at the end of each layer in `pipeline/orchestrator_layers.py`.
 *
 * Order-tolerant: keys may appear in any order; missing keys default to 0.
 */
export function sniffQualityScore(msg: string): QualityScoreLine | null {
  const head = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[QUALITY\\]\\s+L(\\d+)\\s+(.+)$`),
  );
  if (!head) return null;
  const layer = parseInt(head[1]!, 10);
  const rest = head[2]!;
  const pick = (key: string): number => {
    const m = rest.match(new RegExp(`\\b${key}=([0-9.]+)`));
    if (!m) return 0;
    const v = parseFloat(m[1]!);
    return Number.isFinite(v) ? v : 0;
  };
  return {
    layer,
    overall: pick("overall"),
    coherence: pick("coherence"),
    character: pick("character"),
    drama: pick("drama"),
    writing: pick("writing"),
  };
}

export interface AuthorAction {
  name: string;
  role?: string;
  action: string;
}

/**
 * Parse `[AUTHOR] <name>[ · <role>]: <action>` emitted by chapter-writer
 * milestones so the "Hội thoại tác giả" panel populates during L1 generation
 * (which otherwise produces no sniffer-matching log lines).
 *
 * Example: "[AUTHOR] Nhà văn · Layer 1: đang viết Chương 3 - Lập đàn truy hồn"
 *
 * Also tolerates the existing free-text "Đang viết chương N: title..." line
 * emitted by `batch_generator.py:1641` so L1 dead-air is filled without
 * requiring a backend rename.
 */
export function sniffAuthorAction(msg: string): AuthorAction | null {
  const explicit = msg.match(
    new RegExp(`^${LAYER_PREFIX}\\[AUTHOR\\]\\s+([^:·]+?)(?:\\s+·\\s+([^:]+?))?:\\s+(.+?)\\s*$`),
  );
  if (explicit) {
    return {
      name: explicit[1]!.trim(),
      role: explicit[2]?.trim() || undefined,
      action: explicit[3]!.trim(),
    };
  }
  // Vietnamese in-flight form: "Đang viết chương 3: Đại Đạo Triều Thiên..."
  // Treats this as a single virtual author "Nhà văn" actively writing.
  const writing = msg.match(
    new RegExp(`^${LAYER_PREFIX}Đang\\s+viết\\s+ch(?:ương|apter)\\s+(\\d+):\\s*(.+?)\\.{0,3}\\s*$`, "i"),
  );
  if (writing) {
    const num = parseInt(writing[1]!, 10);
    const title = writing[2]!.trim();
    return {
      name: "Nhà văn",
      role: "Layer 1",
      action: `Đang viết Chương ${num}: ${title}`,
    };
  }
  return null;
}
