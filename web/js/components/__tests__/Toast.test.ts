/**
 * Tests for Toast store + per-toast Alpine.data factory.
 *
 * Covers:
 *   - Store push assigns id, defaults, and auto-dismiss timer
 *   - dismiss / clear semantics
 *   - isAssertive variant routing
 *   - toastItem role/aria-live computation by variant
 *   - dismiss() delegates to the store
 *   - window helper binding
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  createToastStore,
  toastItem,
  attachWindowHelper,
  TOAST_DEFAULT_DURATIONS,
  type SfShowToastFn,
} from '../Toast';

describe('createToastStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts empty', () => {
    const s = createToastStore();
    expect(s.items).toEqual([]);
  });

  it('push() appends an item with a fresh id and default duration', () => {
    const s = createToastStore();
    const id = s.push({ message: 'hello' });
    expect(s.items).toHaveLength(1);
    expect(s.items[0].id).toBe(id);
    expect(s.items[0].variant).toBe('info');
    expect(s.items[0].durationMs).toBe(TOAST_DEFAULT_DURATIONS.info);
    expect(typeof s.items[0].createdAt).toBe('number');
  });

  it('mints unique ids across rapid successive pushes', () => {
    const s = createToastStore();
    const ids = [
      s.push({ message: 'a' }),
      s.push({ message: 'b' }),
      s.push({ message: 'c' }),
    ];
    expect(new Set(ids).size).toBe(3);
  });

  it('honours explicit durationMs (including 0 for sticky)', () => {
    const s = createToastStore();
    const id = s.push({ message: 'sticky', durationMs: 0 });
    expect(s.items[0].durationMs).toBe(0);
    // No timer should be scheduled — advancing time leaves the item in place.
    vi.advanceTimersByTime(60_000);
    expect(s.items.find((i) => i.id === id)).toBeDefined();
  });

  it('auto-dismisses after durationMs', () => {
    const s = createToastStore();
    s.push({ message: 'temp', variant: 'success' });
    expect(s.items).toHaveLength(1);
    vi.advanceTimersByTime(TOAST_DEFAULT_DURATIONS.success - 1);
    expect(s.items).toHaveLength(1);
    vi.advanceTimersByTime(2);
    expect(s.items).toHaveLength(0);
  });

  it('error variant uses the longer default duration', () => {
    const s = createToastStore();
    s.push({ message: 'boom', variant: 'error' });
    expect(s.items[0].durationMs).toBe(TOAST_DEFAULT_DURATIONS.error);
  });

  it('dismiss(id) removes only the matching item', () => {
    const s = createToastStore();
    const a = s.push({ message: 'a' });
    const b = s.push({ message: 'b' });
    s.dismiss(a);
    expect(s.items).toHaveLength(1);
    expect(s.items[0].id).toBe(b);
  });

  it('dismiss(id) on an unknown id is a no-op', () => {
    const s = createToastStore();
    s.push({ message: 'a' });
    s.dismiss('does-not-exist');
    expect(s.items).toHaveLength(1);
  });

  it('clear() empties the stack', () => {
    const s = createToastStore();
    s.push({ message: 'a' });
    s.push({ message: 'b' });
    s.clear();
    expect(s.items).toEqual([]);
  });

  it('isAssertive routes warning/error away from info/success', () => {
    const s = createToastStore();
    expect(s.isAssertive('info')).toBe(false);
    expect(s.isAssertive('success')).toBe(false);
    expect(s.isAssertive('warning')).toBe(true);
    expect(s.isAssertive('error')).toBe(true);
  });
});

describe('toastItem', () => {
  it('uses role="status" + aria-live="polite" for info/success', () => {
    const info = toastItem({
      toast: { id: 't1', message: 'm', variant: 'info', durationMs: 0, createdAt: 0 },
    });
    expect(info.role).toBe('status');
    expect(info.ariaLive).toBe('polite');

    const success = toastItem({
      toast: { id: 't2', message: 'm', variant: 'success', durationMs: 0, createdAt: 0 },
    });
    expect(success.role).toBe('status');
    expect(success.ariaLive).toBe('polite');
  });

  it('uses role="alert" + aria-live="assertive" for warning/error', () => {
    const warn = toastItem({
      toast: { id: 't1', message: 'm', variant: 'warning', durationMs: 0, createdAt: 0 },
    });
    expect(warn.role).toBe('alert');
    expect(warn.ariaLive).toBe('assertive');

    const err = toastItem({
      toast: { id: 't2', message: 'm', variant: 'error', durationMs: 0, createdAt: 0 },
    });
    expect(err.role).toBe('alert');
    expect(err.ariaLive).toBe('assertive');
  });

  it('dismiss() delegates to $store.toasts.dismiss with the toast id', () => {
    const store = createToastStore();
    const id = store.push({ message: 'gone' });
    const item = toastItem({
      toast: { id, message: 'gone', variant: 'info', durationMs: 0, createdAt: 0 },
    });
    Object.assign(item, { $store: { toasts: store } });
    item.dismiss();
    expect(store.items.find((i) => i.id === id)).toBeUndefined();
  });

  it('dismiss() is a no-op when $store is unbound', () => {
    const item = toastItem({
      toast: { id: 'orphan', message: 'm', variant: 'info', durationMs: 0, createdAt: 0 },
    });
    expect(() => item.dismiss()).not.toThrow();
  });
});

describe('attachWindowHelper', () => {
  it('exposes window.sfShowToast bound to the store', () => {
    const s = createToastStore();
    attachWindowHelper(s);
    // Cast through the wider Forge signature — globals.d.ts declares the
    // legacy narrow type; the runtime binding is widened by attachWindowHelper.
    const wider = (window as unknown as { sfShowToast: SfShowToastFn }).sfShowToast;
    expect(typeof wider).toBe('function');
    const id = wider('via window', 'success');
    expect(typeof id).toBe('string');
    expect(s.items[0].message).toBe('via window');
    expect(s.items[0].variant).toBe('success');
  });
});
