/**
 * Tests for character-edges.ts — co-occurrence edge derivation.
 *
 * Audit D2 (m2-sse-payload-audit.md) picked the co-occurrence heuristic;
 * these tests pin its semantics:
 *   - edge weight = number of chapters where both names appear
 *   - intensity = weight / max(weight)
 *   - minWeight threshold (default 2) drops noise
 *   - names < 2 chars and missing names are filtered out
 *   - case-insensitive match against chapter content
 */

import { describe, it, expect } from 'vitest';
import { deriveNodes, deriveEdges } from '../character-edges';

const draft = {
  characters: [
    { name: 'An' },
    { name: 'Bình' },
    { name: 'Cường' },
    { name: 'X' },       // filtered: < 2 chars
    { name: '  ' },      // filtered: blank
    { name: '' },        // filtered: blank
  ],
  chapters: [
    { number: 1, content: 'An gặp Bình ở quán trà. Người thứ ba vắng mặt.' },
    { number: 2, content: 'Bình kể chuyện cho An nghe về quá khứ.' },
    { number: 3, content: 'An và Cường đối đầu nhau.' },
    { number: 4, content: 'Cuộc đối thoại giữa Bình, An, và Cường.' },
  ],
};

describe('deriveNodes', () => {
  it('filters short and blank names', () => {
    const nodes = deriveNodes(draft);
    expect(nodes.map((n) => n.name)).toEqual(['An', 'Bình', 'Cường']);
  });

  it('lowercases the id for stable matching', () => {
    const nodes = deriveNodes(draft);
    expect(nodes[0]!.id).toBe('an');
    expect(nodes[1]!.id).toBe('bình');
  });

  it('returns empty for missing or malformed draft', () => {
    expect(deriveNodes(undefined)).toEqual([]);
    expect(deriveNodes({})).toEqual([]);
  });
});

describe('deriveEdges', () => {
  it('counts co-occurrence pairs across chapters', () => {
    const edges = deriveEdges(draft, { minWeight: 1 });
    const byKey = new Map(edges.map((e) => [`${e.sourceId}|${e.targetId}`, e]));
    // An+Bình appear together in ch1, ch2, ch4 → weight 3.
    // An+Cường appear together in ch3, ch4 → weight 2.
    // Bình+Cường appear together in ch4 → weight 1.
    expect(byKey.get('an|bình')?.intensity).toBeCloseTo(1, 5);
    expect(byKey.get('an|cường')?.intensity).toBeCloseTo(2 / 3, 5);
    expect(byKey.get('bình|cường')?.intensity).toBeCloseTo(1 / 3, 5);
  });

  it('respects minWeight threshold', () => {
    const edges = deriveEdges(draft, { minWeight: 2 });
    const keys = edges.map((e) => `${e.sourceId}|${e.targetId}`);
    expect(keys).toContain('an|bình');
    expect(keys).toContain('an|cường');
    expect(keys).not.toContain('bình|cường');
  });

  it('defaults type to neutral', () => {
    const edges = deriveEdges(draft, { minWeight: 1 });
    edges.forEach((e) => expect(e.type).toBe('neutral'));
  });

  it('honors type override', () => {
    const edges = deriveEdges(draft, { minWeight: 1, type: 'rival' });
    edges.forEach((e) => expect(e.type).toBe('rival'));
  });

  it('sorts by descending intensity', () => {
    const edges = deriveEdges(draft, { minWeight: 1 });
    for (let i = 1; i < edges.length; i++) {
      expect(edges[i - 1]!.intensity).toBeGreaterThanOrEqual(edges[i]!.intensity);
    }
  });

  it('returns empty when fewer than 2 valid characters', () => {
    expect(deriveEdges({ characters: [{ name: 'A' }], chapters: draft.chapters })).toEqual([]);
  });

  it('returns empty when chapters are missing or empty', () => {
    expect(deriveEdges({ characters: draft.characters, chapters: [] })).toEqual([]);
    expect(deriveEdges({ characters: draft.characters })).toEqual([]);
  });

  it('is case-insensitive on character match', () => {
    const d = {
      characters: [{ name: 'An' }, { name: 'Bình' }],
      chapters: [{ number: 1, content: 'AN met BÌNH at midnight.' }, { number: 2, content: 'an spoke to bình.' }],
    };
    const edges = deriveEdges(d, { minWeight: 1 });
    expect(edges).toHaveLength(1);
    expect(edges[0]!.intensity).toBeCloseTo(1, 5);
  });
});
