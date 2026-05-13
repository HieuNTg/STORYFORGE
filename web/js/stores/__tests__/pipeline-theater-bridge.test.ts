/**
 * SSE → Theater bridge tests for createPipelineStore().
 *
 * Day-5 scope: verify _theaterReset / _theaterApplyLog / _theaterApplyDone /
 * _theaterApplyError / _theaterApplyInterrupted route correctly to
 * Alpine.store('theater') when registered, and silently no-op when absent.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createPipelineStore } from '../pipeline';

function makeTheaterStub() {
  return {
    reset: vi.fn(),
    applyLog: vi.fn(),
    applyDone: vi.fn(),
    applyError: vi.fn(),
    applyInterrupted: vi.fn(),
  };
}

function setAlpineStores(theater: ReturnType<typeof makeTheaterStub> | null) {
  const w = globalThis as unknown as { Alpine: { store: (k: string) => unknown } };
  w.Alpine = {
    store: (k: string) => {
      if (k === 'theater') return theater;
      if (k === 'app') return { sessionId: null, savePipelineResult: vi.fn() };
      if (k === 'toasts') return undefined;
      return undefined;
    },
  };
}

function fakeStream(events: Array<{ type: string; data?: unknown; session_id?: string }>) {
  return {
    async *[Symbol.asyncIterator]() {
      for (const ev of events) yield ev;
    },
  };
}

describe('pipeline SSE → theater bridge', () => {
  let theater: ReturnType<typeof makeTheaterStub>;

  beforeEach(() => {
    theater = makeTheaterStub();
    setAlpineStores(theater);
    (globalThis as unknown as { API: unknown }).API = { stream: vi.fn() };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('direct _theater* calls no-op when no theater store is registered', () => {
    setAlpineStores(null);
    const p = createPipelineStore();
    expect(() => p._theaterReset()).not.toThrow();
    expect(() => p._theaterApplyLog('x', 1)).not.toThrow();
    expect(() => p._theaterApplyDone({})).not.toThrow();
    expect(() => p._theaterApplyError('boom')).not.toThrow();
    expect(() => p._theaterApplyInterrupted()).not.toThrow();
  });

  it('_theaterReset forwards to the registered store', () => {
    const p = createPipelineStore();
    p._theaterReset();
    expect(theater.reset).toHaveBeenCalledTimes(1);
  });

  it('_theaterApplyLog passes msg + progress through', () => {
    const p = createPipelineStore();
    p._theaterApplyLog('[Agent 1/3] Sage: argue', 1);
    expect(theater.applyLog).toHaveBeenCalledWith('[Agent 1/3] Sage: argue', 1);
  });

  it('_theaterApplyDone forwards the payload', () => {
    const p = createPipelineStore();
    const payload = { data: { draft: { characters: [], chapters: [] } } };
    p._theaterApplyDone(payload);
    expect(theater.applyDone).toHaveBeenCalledWith(payload);
  });

  it('_theaterApplyError forwards the message', () => {
    const p = createPipelineStore();
    p._theaterApplyError('LLM timeout');
    expect(theater.applyError).toHaveBeenCalledWith('LLM timeout');
  });

  it('_theaterApplyInterrupted forwards null when no message given', () => {
    const p = createPipelineStore();
    p._theaterApplyInterrupted();
    expect(theater.applyInterrupted).toHaveBeenCalledWith(null);
  });

  it('end-to-end: _streamPipeline calls reset + applyLog × N + applyDone', async () => {
    const p = createPipelineStore();
    const events = [
      { type: 'log',  data: '[Agent 1/3] Sage: argue' },
      { type: 'log',  data: '[Reader] Simulating chapter 2…' },
      { type: 'done', data: { session_id: 'sid', data: { draft: { characters: [], chapters: [] } } } },
    ];
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream(events),
    );
    await p._streamPipeline('/x', {});

    expect(theater.reset).toHaveBeenCalledTimes(1);
    expect(theater.applyLog).toHaveBeenCalledTimes(2);
    expect(theater.applyLog.mock.calls[0]?.[0]).toBe('[Agent 1/3] Sage: argue');
    expect(theater.applyDone).toHaveBeenCalledTimes(1);
    expect(theater.applyError).not.toHaveBeenCalled();
    expect(theater.applyInterrupted).not.toHaveBeenCalled();
  });

  it('end-to-end: error event routes to applyError, not applyDone', async () => {
    const p = createPipelineStore();
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream([
        { type: 'log',   data: '[Agent 1/3] Sage: argue' },
        { type: 'error', data: 'LLM timeout' },
      ]),
    );
    await p._streamPipeline('/x', {});
    expect(theater.applyError).toHaveBeenCalledWith('LLM timeout');
    expect(theater.applyDone).not.toHaveBeenCalled();
  });

  it('end-to-end: interrupted event routes to applyInterrupted', async () => {
    const p = createPipelineStore();
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream([
        { type: 'log',         data: '[Agent 1/3] Sage: argue' },
        { type: 'interrupted', data: '' },
      ]),
    );
    await p._streamPipeline('/x', {});
    expect(theater.applyInterrupted).toHaveBeenCalledTimes(1);
    expect(theater.applyDone).not.toHaveBeenCalled();
  });

  it('end-to-end: no theater store → _streamPipeline does not throw', async () => {
    setAlpineStores(null);
    const p = createPipelineStore();
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream([
        { type: 'log',  data: '[Agent 1/3] Sage: argue' },
        { type: 'done', data: {} },
      ]),
    );
    await expect(p._streamPipeline('/x', {})).resolves.toBeUndefined();
    // The (null) theater stub means none of the spies should ever fire.
    expect(theater.reset).not.toHaveBeenCalled();
    expect(theater.applyLog).not.toHaveBeenCalled();
  });
});
