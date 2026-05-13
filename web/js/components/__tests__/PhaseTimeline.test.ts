/**
 * Tests for PhaseTimeline factory.
 *
 * Covers:
 *   - Default 8-phase list
 *   - stateFor() computation per (status, currentIndex)
 *   - ARIA value getters
 *   - aria-current="step" only on the active phase
 *   - setCurrentIndex clamps to phase range
 *   - Custom phases prop
 */

import { describe, it, expect } from 'vitest';
import { phaseTimeline, DEFAULT_PHASES, PhaseDef } from '../PhaseTimeline';

describe('phaseTimeline', () => {
  it('initialises with the 8 default phases', () => {
    const t = phaseTimeline();
    expect(t.phases).toHaveLength(8);
    expect(t.phases.map((p) => p.id)).toEqual([
      'theme', 'characters', 'outline', 'conflict',
      'scenes', 'chapters', 'post', 'done',
    ]);
    expect(t.currentIndex).toBe(0);
    expect(t.status).toBe('idle');
  });

  it('aria-valuemax equals phase count', () => {
    const t = phaseTimeline();
    expect(t.ariaValueMax).toBe(8);
  });

  it('aria-valuenow equals currentIndex when running', () => {
    const t = phaseTimeline({ currentIndex: 3, status: 'running' });
    expect(t.ariaValueNow).toBe(3);
  });

  it('aria-valuenow equals phase count when status is done', () => {
    const t = phaseTimeline({ currentIndex: 2, status: 'done' });
    expect(t.ariaValueNow).toBe(8);
  });

  describe('stateFor', () => {
    it('returns done for every phase when status is done', () => {
      const t = phaseTimeline({ status: 'done', currentIndex: 4 });
      for (let i = 0; i < t.phases.length; i++) {
        expect(t.stateFor(i)).toBe('done');
      }
    });

    it('returns done for past phases, active for current, pending for future when running', () => {
      const t = phaseTimeline({ status: 'running', currentIndex: 2 });
      expect(t.stateFor(0)).toBe('done');
      expect(t.stateFor(1)).toBe('done');
      expect(t.stateFor(2)).toBe('active');
      expect(t.stateFor(3)).toBe('pending');
      expect(t.stateFor(7)).toBe('pending');
    });

    it('marks the current phase as error when status is error', () => {
      const t = phaseTimeline({ status: 'error', currentIndex: 3 });
      expect(t.stateFor(2)).toBe('done');
      expect(t.stateFor(3)).toBe('error');
      expect(t.stateFor(4)).toBe('pending');
    });

    it('marks the current phase pending when status is idle (no run started)', () => {
      const t = phaseTimeline({ status: 'idle', currentIndex: 0 });
      expect(t.stateFor(0)).toBe('pending');
    });
  });

  describe('aria-current', () => {
    it('returns "step" only on the active phase', () => {
      const t = phaseTimeline({ status: 'running', currentIndex: 4 });
      expect(t.ariaCurrentFor(3)).toBeUndefined();
      expect(t.ariaCurrentFor(4)).toBe('step');
      expect(t.ariaCurrentFor(5)).toBeUndefined();
    });

    it('returns undefined for every phase when status is done', () => {
      const t = phaseTimeline({ status: 'done', currentIndex: 2 });
      expect(t.ariaCurrentFor(0)).toBeUndefined();
      expect(t.ariaCurrentFor(2)).toBeUndefined();
    });
  });

  describe('setCurrentIndex', () => {
    it('clamps negative values to 0', () => {
      const t = phaseTimeline();
      t.setCurrentIndex(-5);
      expect(t.currentIndex).toBe(0);
    });

    it('clamps overflow to last phase', () => {
      const t = phaseTimeline();
      t.setCurrentIndex(99);
      expect(t.currentIndex).toBe(7);
    });

    it('truncates fractional indices', () => {
      const t = phaseTimeline();
      t.setCurrentIndex(3.8);
      expect(t.currentIndex).toBe(3);
    });
  });

  it('accepts custom phase lists', () => {
    const custom: PhaseDef[] = [
      { id: 'theme', labelKey: 'phase.theme', layer: 1 },
      { id: 'done', labelKey: 'phase.done', layer: 3 },
    ];
    const t = phaseTimeline({ phases: custom, currentIndex: 1, status: 'running' });
    expect(t.phases).toHaveLength(2);
    expect(t.stateFor(0)).toBe('done');
    expect(t.stateFor(1)).toBe('active');
    expect(t.ariaValueMax).toBe(2);
  });

  it('exposes DEFAULT_PHASES as a frozen contract', () => {
    expect(Object.isFrozen(DEFAULT_PHASES)).toBe(true);
  });
});
