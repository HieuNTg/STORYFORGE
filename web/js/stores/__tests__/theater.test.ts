/**
 * Tests for theater.ts — Forge UI pipeline-page derived state.
 *
 * Covers:
 *   - reset() flips pageState idle → generating and wipes derived state
 *   - applyLog routes to the right sniffer:
 *     · [Agent k/N] X: action     → agents stack update
 *     · [AGENTS] Layer N được duyệt → all agents → voting
 *     · [DEBATE] …                → lastDebateMarker captured
 *     · [Reader] Simulating chapter N → readerChapter set
 *     · [StateRegistry] Extracted states for chN → graphTick++
 *   - agent bubble dedupes on same name; trims at 6
 *   - applyDone derives characters + edges from draft, fills quality
 *   - applyError / applyInterrupted update pageState
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { createTheaterStore, type TheaterStore } from '../theater';

let t: TheaterStore;

beforeEach(() => {
  t = createTheaterStore();
});

describe('theater store — initial', () => {
  it('starts idle with empty derived state', () => {
    expect(t.pageState).toBe('idle');
    expect(t.agents).toEqual([]);
    expect(t.characters).toEqual([]);
    expect(t.relationships).toEqual([]);
    expect(t.lastDebateMarker).toBeNull();
    expect(t.readerChapter).toBeNull();
    expect(t.graphTick).toBe(0);
    expect(t.quality).toEqual({ value: 0, dimensions: [] });
  });
});

describe('theater.reset()', () => {
  it('flips pageState to generating and clears everything', () => {
    t.agents.push({ id: 'x', name: 'X', state: 'speaking', message: 'hi', score: null });
    t.characters.push({ id: 'a', name: 'A' });
    t.graphTick = 99;
    t.reset();
    expect(t.pageState).toBe('generating');
    expect(t.agents).toEqual([]);
    expect(t.characters).toEqual([]);
    expect(t.graphTick).toBe(0);
  });
});

describe('theater.applyLog — agent turns', () => {
  it('appends an agent on a fresh [Agent k/N] line', () => {
    t.applyLog('[Agent 1/3] Sage: argue', 1);
    expect(t.agents).toHaveLength(1);
    expect(t.agents[0]).toMatchObject({ name: 'Sage', state: 'debating' });
  });

  it('infers state from the action verb', () => {
    t.applyLog('[Agent 1/3] Sage: think over the plot', 1);
    expect(t.agents[0]!.state).toBe('thinking');
    t.applyLog('[Agent 2/3] Cynic: support', 1);
    expect(t.agents[1]!.state).toBe('speaking');
    t.applyLog('[Agent 3/3] Voter: vote yes', 1);
    expect(t.agents[2]!.state).toBe('voting');
  });

  it('dedupes by agent name, updating the existing bubble in place', () => {
    t.applyLog('[Agent 1/3] Sage: argue', 1);
    t.applyLog('[Agent 1/3] Sage: support', 1);
    expect(t.agents).toHaveLength(1);
    expect(t.agents[0]!.state).toBe('speaking');
    expect(t.agents[0]!.message).toBe('Sage: support');
  });

  it('caps the stack at 6 agents, dropping the oldest', () => {
    for (let i = 0; i < 8; i++) {
      t.applyLog(`[Agent ${i + 1}/8] Agent${i}: argue`, 1);
    }
    expect(t.agents).toHaveLength(6);
    expect(t.agents[0]!.name).toBe('Agent2');
    expect(t.agents[5]!.name).toBe('Agent7');
  });
});

describe('theater.applyLog — phase / debate / reader / registry', () => {
  it('[AGENTS] approved → all agents flip to voting', () => {
    t.applyLog('[Agent 1/3] Sage: argue', 1);
    t.applyLog('[Agent 2/3] Cynic: support', 1);
    t.applyLog('[AGENTS] Layer 1 được duyệt!', 1);
    expect(t.agents.every((a) => a.state === 'voting')).toBe(true);
  });

  it('[DEBATE] freeform captured to lastDebateMarker', () => {
    t.applyLog('[DEBATE] tension peaks at chapter 4', 1);
    expect(t.lastDebateMarker).toBe('tension peaks at chapter 4');
  });

  it('[Reader] chapter N → readerChapter set', () => {
    t.applyLog('[Reader] Simulating chapter 7…', 1);
    expect(t.readerChapter).toBe(7);
  });

  it('[StateRegistry] tick bumps graphTick', () => {
    t.applyLog('[StateRegistry] Extracted states for ch3', 1);
    t.applyLog('[StateRegistry] Extracted states for ch4', 1);
    expect(t.graphTick).toBe(2);
  });

  it('ignores unrelated log lines', () => {
    t.applyLog('random noise', 1);
    t.applyLog('', 0);
    expect(t.agents).toEqual([]);
    expect(t.lastDebateMarker).toBeNull();
    expect(t.readerChapter).toBeNull();
  });
});

describe('theater.applyDone', () => {
  it('derives characters and edges from draft via co-occurrence', () => {
    t.applyDone({
      data: {
        draft: {
          characters: [{ name: 'An' }, { name: 'Bình' }, { name: 'Cường' }],
          chapters: [
            { number: 1, content: 'An gặp Bình.' },
            { number: 2, content: 'An và Bình đối thoại.' },
            { number: 3, content: 'An, Bình, Cường gặp nhau.' },
          ],
        },
      },
    });
    expect(t.pageState).toBe('done');
    expect(t.characters.map((c) => c.name)).toEqual(['An', 'Bình', 'Cường']);
    // an+bình co-occur in 3 chapters → highest intensity = 1.
    const anBinh = t.relationships.find(
      (r) =>
        (r.sourceId === 'an' && r.targetId === 'bình') ||
        (r.sourceId === 'bình' && r.targetId === 'an'),
    );
    expect(anBinh?.intensity).toBeCloseTo(1, 5);
  });

  it('uses quality[] dimensions when available, averaging into overall', () => {
    t.applyDone({
      data: {
        draft: { characters: [], chapters: [] },
        quality: [
          { name: 'coherence', value: 0.8 },
          { name: 'drama', value: 0.6 },
        ],
      },
    });
    expect(t.quality.dimensions).toHaveLength(2);
    expect(t.quality.value).toBeCloseTo(0.7, 5);
  });

  it('falls back to quality_score when no dimensions provided', () => {
    t.applyDone({
      data: {
        draft: { characters: [], chapters: [] },
        quality_score: 0.85,
      },
    });
    expect(t.quality.value).toBeCloseTo(0.85, 5);
    expect(t.quality.dimensions).toEqual([]);
  });

  it('marks live agent bubbles as done', () => {
    t.applyLog('[Agent 1/2] Sage: argue', 1);
    t.applyDone({ data: { draft: { characters: [], chapters: [] } } });
    expect(t.agents.every((a) => a.state === 'done')).toBe(true);
  });
});

describe('theater error transitions', () => {
  it('applyError flips pageState to error', () => {
    t.reset();
    t.applyError('boom');
    expect(t.pageState).toBe('error');
  });

  it('applyInterrupted flips pageState to interrupted', () => {
    t.reset();
    t.applyInterrupted(null);
    expect(t.pageState).toBe('interrupted');
  });
});
