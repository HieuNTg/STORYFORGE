/**
 * Tests for ForgeButton factory.
 *
 * Covers:
 *   - Defaults (label, variant, state, disabled)
 *   - Prop overrides
 *   - ARIA computed getters (aria-busy, aria-disabled)
 *   - setState transitions
 *   - handleClick: dispatches when idle, blocks when loading/disabled
 */

import { describe, it, expect, vi } from 'vitest';
import { forgeButton } from '../ForgeButton';

describe('forgeButton', () => {
  it('uses sensible defaults when no props passed', () => {
    const c = forgeButton();
    expect(c.label).toBe('Forge Story');
    expect(c.variant).toBe('primary');
    expect(c.state).toBe('idle');
    expect(c.disabled).toBe(false);
    expect(c.ariaBusy).toBe('false');
    expect(c.ariaDisabled).toBe('false');
  });

  it('respects props overrides', () => {
    const c = forgeButton({
      label: 'Pause',
      variant: 'danger',
      state: 'loading',
      disabled: false,
    });
    expect(c.label).toBe('Pause');
    expect(c.variant).toBe('danger');
    expect(c.state).toBe('loading');
    expect(c.ariaBusy).toBe('true');
    expect(c.ariaDisabled).toBe('false');
  });

  it('reports aria-disabled when the disabled prop is true', () => {
    const c = forgeButton({ disabled: true });
    expect(c.ariaDisabled).toBe('true');
  });

  it('reports aria-disabled when state is "disabled"', () => {
    const c = forgeButton({ state: 'disabled' });
    expect(c.ariaDisabled).toBe('true');
  });

  it('setState transitions between known states', () => {
    const c = forgeButton();
    c.setState('hover');
    expect(c.state).toBe('hover');
    c.setState('loading');
    expect(c.state).toBe('loading');
    expect(c.ariaBusy).toBe('true');
    c.setState('idle');
    expect(c.state).toBe('idle');
    expect(c.ariaBusy).toBe('false');
  });

  it('handleClick dispatches sf:forge-click when idle', () => {
    const c = forgeButton();
    const dispatch = vi.fn();
    Object.assign(c, { $dispatch: dispatch });
    c.handleClick();
    expect(dispatch).toHaveBeenCalledWith('sf:forge-click', { state: 'idle' });
  });

  it('handleClick blocks and does not dispatch when loading', () => {
    const c = forgeButton({ state: 'loading' });
    const dispatch = vi.fn();
    const event = { preventDefault: vi.fn(), stopPropagation: vi.fn() } as unknown as Event;
    Object.assign(c, { $dispatch: dispatch });
    c.handleClick(event);
    expect(dispatch).not.toHaveBeenCalled();
    expect((event as any).preventDefault).toHaveBeenCalled();
  });

  it('handleClick blocks and does not dispatch when disabled', () => {
    const c = forgeButton({ disabled: true });
    const dispatch = vi.fn();
    Object.assign(c, { $dispatch: dispatch });
    c.handleClick();
    expect(dispatch).not.toHaveBeenCalled();
  });

  it('handleClick is a no-op when no $dispatch is bound (factory called directly)', () => {
    const c = forgeButton();
    // No $dispatch attached — must not throw.
    expect(() => c.handleClick()).not.toThrow();
  });
});
