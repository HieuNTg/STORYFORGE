/**
 * character-edges.ts — derive CharacterGraph edges from `done.data.draft`.
 *
 * The backend `done` summary (api/pipeline_output_builder.py) ships a flat
 * character list but no relationship edges. Spec D2 in
 * plans/.../reports/m2-sse-payload-audit.md picked option 1 (co-occurrence
 * heuristic) as the ship-now path: an edge exists between two characters
 * when both names appear in the same chapter content. Edge weight = count
 * of chapters with co-occurrence.
 *
 * Backend follow-up (out-of-sprint): surface output.conflict_web in the
 * summary builder; once available, this module becomes the fallback.
 *
 * Conservative defaults to limit noise:
 *   - skip names < 2 chars (initials and stop-tokens)
 *   - skip characters with empty/missing names
 *   - edge weight threshold default 2 (set via `minWeight`) to drop spurious
 *     once-mentioned pairs
 *
 * Intensity normalization: weight / max(weight) → [0,1].
 *
 * Type inference: we have no source for ally/enemy/rival at this layer.
 * Default to 'neutral'. A future improvement can re-score via
 * simulation.events[].drama_score (audit D2 option 2).
 */

import type { CharacterEdge, CharacterNode } from '../components/CharacterGraph';

interface ChapterContent {
  number?: number;
  content?: string;
}

interface DraftLike {
  characters?: Array<{ name?: string; personality?: string }>;
  chapters?: ChapterContent[];
}

export interface DeriveEdgeOptions {
  /** Minimum co-occurrence count to emit an edge. Default 2. */
  minWeight?: number;
  /** Override the relationship type assigned. Default 'neutral'. */
  type?: CharacterEdge['type'];
}

/**
 * Build node list from `done.data.draft.characters`. Stable id = lowercased
 * name (matches the same normalization used when scanning chapters).
 */
export function deriveNodes(draft: DraftLike | undefined): CharacterNode[] {
  if (!draft || !Array.isArray(draft.characters)) return [];
  return draft.characters
    .map((c) => (c?.name ?? '').trim())
    .filter((name) => name.length >= 2)
    .map((name) => ({ id: name.toLowerCase(), name }));
}

/**
 * Derive edges via chapter-content co-occurrence. Returns a list sorted by
 * descending intensity for deterministic rendering.
 */
export function deriveEdges(
  draft: DraftLike | undefined,
  options: DeriveEdgeOptions = {},
): CharacterEdge[] {
  const minWeight = options.minWeight ?? 2;
  const type = options.type ?? 'neutral';

  const nodes = deriveNodes(draft);
  if (nodes.length < 2 || !draft || !Array.isArray(draft.chapters)) return [];

  // Pair counts keyed by "idA|idB" with idA < idB to avoid duplicates.
  const pairCounts = new Map<string, number>();

  for (const chapter of draft.chapters) {
    const content = (chapter?.content ?? '').toLowerCase();
    if (content.length === 0) continue;

    // Which characters appear in this chapter?
    const presentIds: string[] = [];
    for (const node of nodes) {
      if (content.includes(node.name.toLowerCase())) {
        presentIds.push(node.id);
      }
    }

    // For every pair present, increment.
    for (let i = 0; i < presentIds.length; i++) {
      for (let j = i + 1; j < presentIds.length; j++) {
        const a = presentIds[i]!;
        const b = presentIds[j]!;
        const key = a < b ? `${a}|${b}` : `${b}|${a}`;
        pairCounts.set(key, (pairCounts.get(key) ?? 0) + 1);
      }
    }
  }

  // Find max weight for intensity normalization.
  let maxWeight = 0;
  for (const weight of pairCounts.values()) {
    if (weight > maxWeight) maxWeight = weight;
  }
  if (maxWeight === 0) return [];

  const edges: CharacterEdge[] = [];
  for (const [key, weight] of pairCounts.entries()) {
    if (weight < minWeight) continue;
    const [sourceId, targetId] = key.split('|') as [string, string];
    edges.push({
      sourceId,
      targetId,
      type,
      intensity: weight / maxWeight,
    });
  }

  edges.sort((a, b) => b.intensity - a.intensity);
  return edges;
}
