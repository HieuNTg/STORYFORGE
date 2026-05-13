/**
 * Tests for QualityGauge Alpine.data factory.
 *
 * Covers:
 *   - Defaults + prop overrides
 *   - Scale normalization (0-1 vs 0-5)
 *   - Color band thresholds (danger / forge / complete)
 *   - Arc geometry: dasharray, dashoffset, endpoint
 *   - Radar polygon: 3+ dims → points, <3 → empty
 *   - ariaLabel composition
 *   - setValue / setDimensions / setState behaviour
 *   - State machine: empty → scored on positive value
 */

import { describe, it, expect } from 'vitest';
import { qualityGauge } from '../QualityGauge';

describe('qualityGauge', () => {
  it('uses sane defaults', () => {
    const g = qualityGauge();
    expect(g.value).toBe(0);
    expect(g.scale).toBe('0-1');
    expect(g.label).toBe('');
    expect(g.size).toBe('md');
    expect(g.dimensions).toEqual([]);
    expect(g.state).toBe('empty');
    expect(g.progress).toBe(0);
    expect(g.band).toBe('danger');
  });

  it('flips state to scored when initial value > 0', () => {
    const g = qualityGauge({ value: 0.5 });
    expect(g.state).toBe('scored');
  });

  describe('scale normalization', () => {
    it('passes 0-1 value through unchanged', () => {
      const g = qualityGauge({ value: 0.75, scale: '0-1' });
      expect(g.progress).toBe(0.75);
      expect(g.displayMax).toBe(1);
      expect(g.displayValue).toBe('0.75');
    });

    it('divides 0-5 value by 5', () => {
      const g = qualityGauge({ value: 4, scale: '0-5' });
      expect(g.progress).toBe(0.8);
      expect(g.displayMax).toBe(5);
      expect(g.displayValue).toBe('4.0');
    });

    it('clamps progress to [0,1]', () => {
      const over = qualityGauge({ value: 9, scale: '0-5' });
      expect(over.progress).toBe(1);
      const neg = qualityGauge({ value: -1, scale: '0-1' });
      expect(neg.progress).toBe(0);
    });

    it('handles NaN as 0 progress', () => {
      const g = qualityGauge({ value: Number.NaN });
      expect(g.progress).toBe(0);
    });
  });

  describe('color band', () => {
    it('returns danger below 0.4', () => {
      expect(qualityGauge({ value: 0.39 }).band).toBe('danger');
    });

    it('returns forge in [0.4, 0.7)', () => {
      expect(qualityGauge({ value: 0.4 }).band).toBe('forge');
      expect(qualityGauge({ value: 0.69 }).band).toBe('forge');
    });

    it('returns complete at or above 0.7', () => {
      expect(qualityGauge({ value: 0.7 }).band).toBe('complete');
      expect(qualityGauge({ value: 1 }).band).toBe('complete');
    });

    it('respects scale when computing band (3/5 = 0.6 → forge)', () => {
      expect(qualityGauge({ value: 3, scale: '0-5' }).band).toBe('forge');
    });
  });

  describe('geometry', () => {
    it('produces a non-zero circumference and dasharray string', () => {
      const g = qualityGauge({ value: 0.5 });
      const geo = g.geometry;
      expect(geo.cx).toBe(50);
      expect(geo.cy).toBe(50);
      expect(geo.radius).toBe(42);
      expect(geo.circumference).toBeCloseTo(2 * Math.PI * 42, 5);
      expect(geo.dasharray).toMatch(/^[\d.]+\s[\d.]+$/);
    });

    it('reduces dashoffset to 0 at progress=1', () => {
      const g = qualityGauge({ value: 1 });
      expect(g.geometry.dashoffset).toBeCloseTo(0, 5);
    });

    it('leaves dashoffset = arcLength at progress=0', () => {
      const g = qualityGauge({ value: 0 });
      const expected = 2 * Math.PI * 42 * 0.75;
      expect(g.geometry.dashoffset).toBeCloseTo(expected, 5);
    });

    it('endpoint sits on the gauge ring', () => {
      const g = qualityGauge({ value: 0.5 });
      const { x, y } = g.geometry.endpoint;
      const distance = Math.hypot(x - 50, y - 50);
      expect(distance).toBeCloseTo(42, 5);
    });
  });

  describe('radar', () => {
    it('emits no points when fewer than 3 dimensions', () => {
      const g = qualityGauge({
        dimensions: [
          { name: 'a', value: 0.5 },
          { name: 'b', value: 0.7 },
        ],
      });
      expect(g.hasRadar).toBe(false);
      expect(g.radarPoints).toBe('');
    });

    it('emits one "x,y" pair per dimension when 3+', () => {
      const g = qualityGauge({
        dimensions: [
          { name: 'coherence', value: 0.8 },
          { name: 'character', value: 0.6 },
          { name: 'drama', value: 0.9 },
          { name: 'writing', value: 0.7 },
        ],
      });
      expect(g.hasRadar).toBe(true);
      const pairs = g.radarPoints.split(' ');
      expect(pairs).toHaveLength(4);
      pairs.forEach((p) => expect(p).toMatch(/^[-\d.]+,[-\d.]+$/));
    });

    it('respects gauge scale when normalizing dimension values', () => {
      const g = qualityGauge({
        scale: '0-5',
        dimensions: [
          { name: 'a', value: 5 }, // max → at outer radar radius
          { name: 'b', value: 0 }, // min → at center
          { name: 'c', value: 2.5 }, // midpoint
        ],
      });
      // First dim is at top of radar (angle = -π/2), full magnitude.
      const innerR = 42 * 0.6;
      const firstPair = g.radarPoints.split(' ')[0]!;
      const [x, y] = firstPair.split(',').map(Number);
      expect(x).toBeCloseTo(50, 1);
      expect(y).toBeCloseTo(50 - innerR, 1); // straight up
    });
  });

  describe('ariaLabel', () => {
    it('includes value and max for 0-1 scale', () => {
      const g = qualityGauge({ value: 0.85 });
      expect(g.ariaLabel).toBe('Quality score: 0.85 out of 1');
    });

    it('formats 0-5 scale with one decimal', () => {
      const g = qualityGauge({ value: 3.4, scale: '0-5' });
      expect(g.ariaLabel).toBe('Quality score: 3.4 out of 5');
    });

    it('prepends label when provided', () => {
      const g = qualityGauge({ value: 0.6, label: 'Drama' });
      expect(g.ariaLabel).toBe('Drama Quality score: 0.60 out of 1');
    });
  });

  describe('setters', () => {
    it('setValue updates value and state', () => {
      const g = qualityGauge();
      g.setValue(0.5);
      expect(g.value).toBe(0.5);
      expect(g.state).toBe('scored');
      g.setValue(0);
      expect(g.state).toBe('empty');
    });

    it('setValue ignores non-finite input', () => {
      const g = qualityGauge({ value: 0.5 });
      g.setValue(Number.NaN);
      expect(g.value).toBe(0.5);
      g.setValue(Number.POSITIVE_INFINITY);
      expect(g.value).toBe(0.5);
    });

    it('setDimensions replaces the array', () => {
      const g = qualityGauge();
      g.setDimensions([{ name: 'x', value: 0.3 }, { name: 'y', value: 0.4 }, { name: 'z', value: 0.5 }]);
      expect(g.dimensions).toHaveLength(3);
      expect(g.hasRadar).toBe(true);
      g.setDimensions(undefined);
      expect(g.dimensions).toEqual([]);
      expect(g.hasRadar).toBe(false);
    });

    it('setState accepts valid values only', () => {
      const g = qualityGauge();
      g.setState('scoring');
      expect(g.state).toBe('scoring');
      g.setState('garbage' as unknown as 'empty');
      expect(g.state).toBe('scoring');
    });
  });

  describe('prefersReducedMotion', () => {
    it('honors the prop override', () => {
      const on = qualityGauge({ prefersReducedMotion: true });
      const off = qualityGauge({ prefersReducedMotion: false });
      expect(on.prefersReducedMotion).toBe(true);
      expect(off.prefersReducedMotion).toBe(false);
    });
  });
});
