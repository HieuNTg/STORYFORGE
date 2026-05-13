/**
 * Tests for AgentBubble Alpine.data factory.
 *
 * Covers:
 *   - Defaults + prop overrides
 *   - State setter input validation
 *   - Score clamping and scorePct computation (voting state only)
 *   - Typewriter: tick semantics, reduced-motion bypass, restart on setMessage
 *   - revealPct computation
 *   - ariaLabel composition
 *   - handleClick dispatch + stopPropagation
 *   - init wires $watch('message'); destroy cancels timer
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { agentBubble, type AgentBubbleComponent } from '../AgentBubble';

describe('agentBubble', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('uses sane defaults when only required props are supplied', () => {
    const c = agentBubble({ agentId: 'sage', name: 'Sage', prefersReducedMotion: true });
    expect(c.agentId).toBe('sage');
    expect(c.name).toBe('Sage');
    expect(c.avatar).toBe('');
    expect(c.state).toBe('idle');
    expect(c.message).toBe('');
    expect(c.score).toBeNull();
    expect(c.compact).toBe(false);
    expect(c.revealedChars).toBe(0);
  });

  it('respects every prop when supplied', () => {
    const c = agentBubble({
      agentId: 'cynic',
      name: 'Cynic',
      avatar: '/img/c.png',
      state: 'debating',
      message: 'Hello',
      score: 0.42,
      compact: true,
      prefersReducedMotion: true,
    });
    expect(c.avatar).toBe('/img/c.png');
    expect(c.state).toBe('debating');
    expect(c.message).toBe('Hello');
    expect(c.score).toBe(0.42);
    expect(c.compact).toBe(true);
  });

  it('falls back to idle when an unknown state is supplied', () => {
    const c = agentBubble({
      agentId: 'a',
      name: 'A',
      state: 'bogus' as unknown as 'idle',
      prefersReducedMotion: true,
    });
    expect(c.state).toBe('idle');
  });

  describe('score', () => {
    it('clamps to [0,1]', () => {
      const over = agentBubble({ agentId: 'a', name: 'A', score: 9, prefersReducedMotion: true });
      expect(over.score).toBe(1);
      const neg = agentBubble({ agentId: 'a', name: 'A', score: -2, prefersReducedMotion: true });
      expect(neg.score).toBe(0);
    });

    it('rejects NaN and undefined as null', () => {
      const nan = agentBubble({
        agentId: 'a', name: 'A', score: Number.NaN, prefersReducedMotion: true,
      });
      expect(nan.score).toBeNull();
      const u = agentBubble({ agentId: 'a', name: 'A', prefersReducedMotion: true });
      expect(u.score).toBeNull();
    });

    it('scorePct is null unless state is voting', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', score: 0.5, state: 'speaking', prefersReducedMotion: true,
      });
      expect(c.scorePct).toBeNull();
      c.setState('voting');
      expect(c.scorePct).toBe(50);
    });

    it('setScore clamps and accepts null', () => {
      const c = agentBubble({ agentId: 'a', name: 'A', prefersReducedMotion: true });
      c.setScore(2);
      expect(c.score).toBe(1);
      c.setScore(null);
      expect(c.score).toBeNull();
    });
  });

  describe('setState', () => {
    it('ignores invalid state values', () => {
      const c = agentBubble({ agentId: 'a', name: 'A', state: 'thinking', prefersReducedMotion: true });
      c.setState('garbage' as unknown as 'idle');
      expect(c.state).toBe('thinking');
    });

    it('accepts valid state values', () => {
      const c = agentBubble({ agentId: 'a', name: 'A', prefersReducedMotion: true });
      c.setState('done');
      expect(c.state).toBe('done');
    });
  });

  describe('typewriter', () => {
    it('reveals all chars instantly when reduced-motion is on', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'hello', prefersReducedMotion: true,
      });
      expect(c.revealedChars).toBe(5);
      expect(c.revealPct).toBe(100);
    });

    it('starts reveal at 0 when typewriter is active', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'hello', prefersReducedMotion: false,
      });
      // Constructor does not auto-start; init() does. Manually start here.
      c.startTypewriter();
      expect(c.revealedChars).toBe(0);
      expect(c.revealPct).toBe(0);
    });

    it('advances one char per scheduled step', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'abc',
        prefersReducedMotion: false, typewriterStepMs: 25,
      });
      c.startTypewriter();
      expect(c.revealedChars).toBe(0);
      vi.advanceTimersByTime(25);
      expect(c.revealedChars).toBe(1);
      vi.advanceTimersByTime(25);
      expect(c.revealedChars).toBe(2);
      vi.advanceTimersByTime(25);
      expect(c.revealedChars).toBe(3);
      vi.advanceTimersByTime(25);
      expect(c.revealedChars).toBe(3); // capped
    });

    it('stopTypewriter cancels further ticks', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'abcdef',
        prefersReducedMotion: false, typewriterStepMs: 25,
      });
      c.startTypewriter();
      vi.advanceTimersByTime(25);
      expect(c.revealedChars).toBe(1);
      c.stopTypewriter();
      vi.advanceTimersByTime(1000);
      expect(c.revealedChars).toBe(1);
    });

    it('setMessage replaces text and restarts the reveal', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'old',
        prefersReducedMotion: false, typewriterStepMs: 10,
      });
      c.startTypewriter();
      vi.advanceTimersByTime(10);
      expect(c.revealedChars).toBe(1);
      c.setMessage('new content');
      expect(c.message).toBe('new content');
      expect(c.revealedChars).toBe(0);
      vi.advanceTimersByTime(10);
      expect(c.revealedChars).toBe(1);
    });

    it('tickTypewriter returns false when message is fully revealed', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'ab', prefersReducedMotion: false,
      });
      expect(c.tickTypewriter()).toBe(true);
      expect(c.tickTypewriter()).toBe(false);
      expect(c.tickTypewriter()).toBe(false);
    });

    it('revealPct is 100 for empty message regardless of revealedChars', () => {
      const c = agentBubble({ agentId: 'a', name: 'A', prefersReducedMotion: false });
      expect(c.revealPct).toBe(100);
    });
  });

  describe('ariaLabel', () => {
    it('composes name and state', () => {
      const c = agentBubble({
        agentId: 'a', name: 'Sage', state: 'thinking', prefersReducedMotion: true,
      });
      expect(c.ariaLabel).toBe('Sage agent, currently thinking');
    });

    it('updates when state changes', () => {
      const c = agentBubble({ agentId: 'a', name: 'Sage', prefersReducedMotion: true });
      c.setState('voting');
      expect(c.ariaLabel).toBe('Sage agent, currently voting');
    });
  });

  describe('handleClick', () => {
    it('dispatches sf:agent-clicked with the agentId', () => {
      const c = agentBubble({ agentId: 'cynic', name: 'Cynic', prefersReducedMotion: true });
      const dispatch = vi.fn();
      Object.assign(c, { $dispatch: dispatch });
      c.handleClick();
      expect(dispatch).toHaveBeenCalledWith('sf:agent-clicked', { agentId: 'cynic' });
    });

    it('stops propagation when given an event', () => {
      const c = agentBubble({ agentId: 'a', name: 'A', prefersReducedMotion: true });
      const dispatch = vi.fn();
      const event = { stopPropagation: vi.fn() } as unknown as Event;
      Object.assign(c, { $dispatch: dispatch });
      c.handleClick(event);
      expect((event as unknown as { stopPropagation: ReturnType<typeof vi.fn> }).stopPropagation).toHaveBeenCalled();
    });

    it('is a no-op when $dispatch is unbound', () => {
      const c = agentBubble({ agentId: 'a', name: 'A', prefersReducedMotion: true });
      expect(() => c.handleClick()).not.toThrow();
    });
  });

  describe('lifecycle', () => {
    it('init wires $watch("message") and starts typewriter for non-empty initial message', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'hi',
        prefersReducedMotion: false, typewriterStepMs: 10,
      });
      const watch = vi.fn();
      Object.assign(c, { $watch: watch });
      c.init();
      expect(watch).toHaveBeenCalledWith('message', expect.any(Function));
      expect(c.revealedChars).toBe(0);
      vi.advanceTimersByTime(10);
      expect(c.revealedChars).toBe(1);
    });

    it('init does not start ticker when reduced-motion is on', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'hi', prefersReducedMotion: true,
      });
      const watch = vi.fn();
      Object.assign(c, { $watch: watch });
      c.init();
      expect(c.revealedChars).toBe(2);
      // No pending timer.
      expect((c as unknown as AgentBubbleComponent)._typewriterTimer).toBeNull();
    });

    it('destroy stops any pending timer', () => {
      const c = agentBubble({
        agentId: 'a', name: 'A', message: 'abcdef',
        prefersReducedMotion: false, typewriterStepMs: 10,
      });
      c.startTypewriter();
      expect((c as unknown as AgentBubbleComponent)._typewriterTimer).not.toBeNull();
      c.destroy();
      expect((c as unknown as AgentBubbleComponent)._typewriterTimer).toBeNull();
    });
  });
});
