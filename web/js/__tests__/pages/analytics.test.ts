/**
 * pages/analytics.test.ts
 *
 * Unit tests for analyticsPage() factory.
 *
 * Covers:
 *   - Default state shape
 *   - compute() with no result: stats = null, loaded = false
 *   - compute() with empty chapters: stats = null
 *   - compute() happy path: totalWords, avgWords, readingTime, totalChapters
 *   - compute() is idempotent when result ref unchanged
 *   - result getter: uses saved when storySource = 'saved'
 *   - result getter: uses pipelineResult when storySource = 'current'
 *   - hasCurrentResult: true/false based on Alpine.store('app').pipelineResult
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { analyticsPage } from '../../pages/analytics';

describe('analyticsPage', () => {
  beforeEach(() => {
    vi.mocked(Alpine.store).mockReturnValue(null);
  });

  it('defaults: loaded=false, stats=null, storySource=current', () => {
    const a = analyticsPage();
    expect(a.loaded).toBe(false);
    expect(a.stats).toBeNull();
    expect(a.storySource).toBe('current');
    expect(a.stories).toEqual([]);
  });

  it('compute() does nothing when result is null', () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({ pipelineResult: null, status: 'idle' }));
    const a = analyticsPage();
    a.compute();
    expect(a.stats).toBeNull();
    expect(a.loaded).toBe(false);
  });

  it('compute() does nothing when result has no chapters', () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({
      pipelineResult: { enhanced: { title: 'T' } },
      status: 'idle',
    }));
    const a = analyticsPage();
    a.compute();
    expect(a.stats).toBeNull();
    expect(a.loaded).toBe(false);
  });

  it('compute() calculates correct stats for 2 chapters', () => {
    const ch1 = { content: 'one two three' };   // 3 words
    const ch2 = { content: 'a b c d e f g' };  // 7 words
    vi.mocked(Alpine.store).mockImplementation(() => ({
      pipelineResult: { enhanced: { chapters: [ch1, ch2] } },
      status: 'idle',
    }));
    const a = analyticsPage();
    a.compute();
    expect(a.loaded).toBe(true);
    expect(a.stats).not.toBeNull();
    expect(a.stats!.totalChapters).toBe(2);
    expect(a.stats!.totalWords).toBe(10);
    expect(a.stats!.avgWords).toBe(5);
    expect(a.stats!.readingTime).toBe(1); // ceil(10/200) = 1
  });

  it('compute() is idempotent when result ref unchanged', () => {
    const ch = { content: 'word word' };
    const pipelineResult = { enhanced: { chapters: [ch] } };
    vi.mocked(Alpine.store).mockImplementation(() => ({ pipelineResult, status: 'idle' }));
    const a = analyticsPage();
    a.compute();
    const firstStats = a.stats;
    a.compute();
    // Should return early (ref unchanged) — same object identity
    expect(a.stats).toBe(firstStats);
  });

  it('result getter uses pipelineResult when storySource = current', () => {
    const pr = { enhanced: { chapters: [] } };
    vi.mocked(Alpine.store).mockImplementation(() => ({ pipelineResult: pr, status: 'idle' }));
    const a = analyticsPage();
    expect(a.result).toBe(pr);
  });

  it('result getter uses loadedResult when storySource = saved', () => {
    const saved = { draft: { chapters: [] } };
    vi.mocked(Alpine.store).mockImplementation(() => ({ pipelineResult: null, status: 'idle' }));
    const a = analyticsPage();
    a.storySource = 'saved';
    a.loadedResult = saved;
    expect(a.result).toBe(saved);
  });

  it('hasCurrentResult is true when pipelineResult is set', () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({
      pipelineResult: { enhanced: { chapters: [] } },
      status: 'idle',
    }));
    const a = analyticsPage();
    expect(a.hasCurrentResult).toBe(true);
  });

  it('hasCurrentResult is false when pipelineResult is null', () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({ pipelineResult: null, status: 'idle' }));
    const a = analyticsPage();
    expect(a.hasCurrentResult).toBe(false);
  });

  it('useCurrent() resets to current source and clears loadedResult', () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({ pipelineResult: null, status: 'idle' }));
    const a = analyticsPage();
    a.storySource = 'saved';
    a.loadedResult = { draft: { chapters: [] } };
    a.useCurrent();
    expect(a.storySource).toBe('current');
    expect(a.loadedResult).toBeNull();
  });

  it('compute() includes quality from result', () => {
    const quality = [{ layer: 1, overall: 4.2, coherence: 4.0, character: 4.5, drama: 4.1, writing: 4.2 }];
    vi.mocked(Alpine.store).mockImplementation(() => ({
      pipelineResult: { enhanced: { chapters: [{ content: 'a b' }] }, quality },
      status: 'idle',
    }));
    const a = analyticsPage();
    a.compute();
    expect(a.stats!.quality).toBe(quality);
  });

  it('compute() sets hasSimulation when simulation present', () => {
    vi.mocked(Alpine.store).mockImplementation(() => ({
      pipelineResult: {
        enhanced: { chapters: [{ content: 'hi there' }] },
        simulation: { events_count: 42 },
      },
      status: 'idle',
    }));
    const a = analyticsPage();
    a.compute();
    expect(a.stats!.hasSimulation).toBe(true);
    expect(a.stats!.eventsCount).toBe(42);
  });
});
