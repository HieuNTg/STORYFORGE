/**
 * SSE → Toast bridge tests for createPipelineStore().
 *
 * Day-4 scope: verify that the additive _emitToast/_sniffChapterCompletion
 * helpers behave correctly. The streaming path itself is exercised via a
 * fake async iterable handed to API.stream — we mock window.API so we never
 * touch the real fetch.
 *
 * The bridge must:
 *   - Push 'Generation started' info on stream entry
 *   - Push success on chapter-complete log lines
 *   - Push info on L1 → L2 transition (not 0→1, not within-phase)
 *   - Push sticky success ({durationMs:0}) on done event
 *   - Push error on error event
 *   - Push warning on interrupted event
 *   - Silently no-op when no `toasts` store is registered (legacy mode)
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createPipelineStore } from '../pipeline';

interface PushedToast {
  message: string;
  variant: 'info' | 'success' | 'warning' | 'error';
  durationMs?: number;
}

function makeToastStoreStub() {
  const items: PushedToast[] = [];
  return {
    items,
    push: vi.fn((t: PushedToast) => {
      items.push(t);
      return `id-${items.length}`;
    }),
  };
}

/**
 * Wire window.Alpine.store('toasts') to the supplied stub (or remove it).
 * createPipelineStore() resolves Alpine lazily inside _emitToast, so we just
 * patch the global before each call.
 */
function setAlpineToastStore(stub: ReturnType<typeof makeToastStoreStub> | null) {
  const w = globalThis as unknown as {
    Alpine?: { store: (k: string) => unknown };
  };
  w.Alpine = {
    store: (k: string) => (k === 'toasts' ? stub : undefined),
  };
}

function fakeStream(events: Array<{ type: string; data?: unknown; session_id?: string }>) {
  return {
    async *[Symbol.asyncIterator]() {
      for (const ev of events) yield ev;
    },
  };
}

describe('pipeline SSE → toast bridge', () => {
  let toasts: ReturnType<typeof makeToastStoreStub>;

  beforeEach(() => {
    toasts = makeToastStoreStub();
    setAlpineToastStore(toasts);
    // Mock window.API with a stream() that returns whatever the test queues.
    (globalThis as unknown as { API: unknown }).API = {
      stream: vi.fn(),
    };
    // Stub Alpine.store('app') and ('pipeline') reads from _streamPipeline.
    const w = globalThis as unknown as { Alpine: { store: (k: string) => unknown } };
    const prevStore = w.Alpine.store;
    w.Alpine.store = (k: string) => {
      if (k === 'toasts') return toasts;
      if (k === 'app') return { sessionId: null, savePipelineResult: vi.fn() };
      return prevStore(k);
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('_emitToast is a no-op when no toast store is registered', () => {
    setAlpineToastStore(null);
    const p = createPipelineStore();
    // Direct call — should not throw.
    expect(() => p._emitToast('info', 'should not show')).not.toThrow();
  });

  it('_emitToast pushes to the registered store with passthrough payload', () => {
    const p = createPipelineStore();
    p._emitToast('error', 'boom', 0);
    expect(toasts.push).toHaveBeenCalledWith({
      message: 'boom',
      variant: 'error',
      durationMs: 0,
    });
  });

  it('_sniffChapterCompletion parses Vietnamese chapter-complete lines', () => {
    const p = createPipelineStore();
    expect(p._sniffChapterCompletion('✅ Chương 3: Đại Đạo')).toBe('Ch. 3 — Đại Đạo');
    expect(p._sniffChapterCompletion('Chương 12: Kết thúc')).toBe('Ch. 12 — Kết thúc');
    expect(p._sniffChapterCompletion('Chapter 1: Beginning')).toBe('Ch. 1 — Beginning');
    expect(p._sniffChapterCompletion('Layer 2 starting')).toBeNull();
    expect(p._sniffChapterCompletion('arbitrary log')).toBeNull();
  });

  it('emits info on stream entry, success on chapter complete, info on L1→L2, sticky success on done', async () => {
    const p = createPipelineStore();
    const events = [
      { type: 'log',  data: 'Layer 1 starting' },
      { type: 'log',  data: '✅ Chương 1: Khởi đầu' },
      { type: 'log',  data: 'Layer 2 starting' },
      { type: 'done', data: { session_id: 'sid' } },
    ];
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream(events),
    );
    await p._streamPipeline('/x', {});

    const calls = toasts.push.mock.calls.map((c: [PushedToast]) => c[0]);
    expect(calls[0]).toEqual({ message: 'Generation started', variant: 'info', durationMs: undefined });
    expect(calls.some((t: PushedToast) => t.variant === 'success' && t.message.startsWith('Chapter complete'))).toBe(true);
    expect(calls.some((t: PushedToast) => t.variant === 'info' && t.message.startsWith('Layer 2'))).toBe(true);
    // Sticky success on done — durationMs explicitly 0.
    const last = calls[calls.length - 1];
    expect(last).toEqual({ message: 'Generation complete', variant: 'success', durationMs: 0 });
  });

  it('emits error toast on error event', async () => {
    const p = createPipelineStore();
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream([
        { type: 'log',   data: 'Layer 1 ok' },
        { type: 'error', data: 'LLM timeout' },
      ]),
    );
    await p._streamPipeline('/x', {});
    const calls = toasts.push.mock.calls.map((c: [PushedToast]) => c[0]);
    expect(calls.find((t: PushedToast) => t.variant === 'error')).toEqual({
      message: 'LLM timeout', variant: 'error', durationMs: undefined,
    });
  });

  it('emits warning toast on interrupted event', async () => {
    const p = createPipelineStore();
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream([
        { type: 'log',         data: 'Layer 1 progressing' },
        { type: 'interrupted', data: '' },
      ]),
    );
    await p._streamPipeline('/x', {});
    const calls = toasts.push.mock.calls.map((c: [PushedToast]) => c[0]);
    expect(calls.find((t: PushedToast) => t.variant === 'warning')?.message).toMatch(/Connection lost/);
  });

  it('does NOT emit chapter-complete toast for arbitrary log lines', async () => {
    const p = createPipelineStore();
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream([
        { type: 'log',  data: 'Layer 1 starting' },
        { type: 'log',  data: 'Outline complete' },
        { type: 'done', data: {} },
      ]),
    );
    await p._streamPipeline('/x', {});
    const calls = toasts.push.mock.calls.map((c: [PushedToast]) => c[0]);
    expect(calls.find((t: PushedToast) => t.message.startsWith('Chapter complete'))).toBeUndefined();
  });

  it('all _streamPipeline calls remain side-effect-free for the toast store when none is registered', async () => {
    // Detach the toast store so push() must NOT be invoked.
    setAlpineToastStore(null);
    const p = createPipelineStore();
    (globalThis as unknown as { API: { stream: ReturnType<typeof vi.fn> } }).API.stream.mockReturnValue(
      fakeStream([
        { type: 'log',  data: 'Layer 1' },
        { type: 'done', data: {} },
      ]),
    );
    await expect(p._streamPipeline('/x', {})).resolves.toBeUndefined();
    // toasts.push should not have been called because the store wasn't resolved.
    expect(toasts.push).not.toHaveBeenCalled();
  });
});
