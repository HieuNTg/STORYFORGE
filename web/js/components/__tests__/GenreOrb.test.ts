/**
 * Tests for GenreOrb factory.
 *
 * Covers:
 *   - Decorative default + aria-hidden behaviour
 *   - orbStyle exposes --orb-hue
 *   - Selection state + aria-checked
 *   - handleClick dispatches sf:genre-selected when interactive
 *   - handleClick is a no-op when decorative
 *   - GENRE_HUE mapping integrity
 */

import { describe, it, expect, vi } from 'vitest';
import { genreOrb, GENRE_HUE } from '../GenreOrb';

describe('genreOrb', () => {
  it('defaults to decorative (aria-hidden true) and unselected', () => {
    const c = genreOrb({ genreId: 'tien-hiep', hue: '#10B981' });
    expect(c.decorative).toBe(true);
    expect(c.ariaHidden).toBe('true');
    expect(c.selected).toBe(false);
    expect(c.ariaChecked).toBe('false');
  });

  it('exposes --orb-hue via orbStyle', () => {
    const c = genreOrb({ genreId: 'do-thi', hue: '#F43F5E' });
    expect(c.orbStyle).toBe('--orb-hue: #F43F5E;');
  });

  it('uses genreId as default label when none supplied', () => {
    const c = genreOrb({ genreId: 'huyen-huyen', hue: '#8B5CF6' });
    expect(c.label).toBe('huyen-huyen');
  });

  it('respects label and selected props', () => {
    const c = genreOrb({
      genreId: 'xuyen-khong',
      hue: '#F59E0B',
      label: 'Xuyên Không',
      decorative: false,
      selected: true,
    });
    expect(c.label).toBe('Xuyên Không');
    expect(c.decorative).toBe(false);
    expect(c.ariaHidden).toBeUndefined();
    expect(c.selected).toBe(true);
    expect(c.ariaChecked).toBe('true');
  });

  it('setSelected mutates state and updates ariaChecked', () => {
    const c = genreOrb({ genreId: 'tien-hiep', hue: '#10B981', decorative: false });
    expect(c.ariaChecked).toBe('false');
    c.setSelected(true);
    expect(c.selected).toBe(true);
    expect(c.ariaChecked).toBe('true');
  });

  describe('handleClick', () => {
    it('dispatches sf:genre-selected when interactive', () => {
      const c = genreOrb({
        genreId: 'tien-hiep',
        hue: '#10B981',
        decorative: false,
      });
      const dispatch = vi.fn();
      Object.assign(c, { $dispatch: dispatch });
      c.handleClick();
      expect(dispatch).toHaveBeenCalledWith('sf:genre-selected', {
        genreId: 'tien-hiep',
        hue: '#10B981',
      });
    });

    it('is a no-op when decorative (and prevents default)', () => {
      const c = genreOrb({ genreId: 'tien-hiep', hue: '#10B981' });
      const dispatch = vi.fn();
      const event = { preventDefault: vi.fn() } as unknown as Event;
      Object.assign(c, { $dispatch: dispatch });
      c.handleClick(event);
      expect(dispatch).not.toHaveBeenCalled();
      expect((event as any).preventDefault).toHaveBeenCalled();
    });

    it('does not throw when $dispatch is absent (factory called directly)', () => {
      const c = genreOrb({
        genreId: 'tien-hiep',
        hue: '#10B981',
        decorative: false,
      });
      expect(() => c.handleClick()).not.toThrow();
    });
  });

  describe('GENRE_HUE contract', () => {
    it('contains the four canonical PRD genres', () => {
      expect(GENRE_HUE['tien-hiep']).toBe('#10B981');
      expect(GENRE_HUE['do-thi']).toBe('#F43F5E');
      expect(GENRE_HUE['huyen-huyen']).toBe('#8B5CF6');
      expect(GENRE_HUE['xuyen-khong']).toBe('#F59E0B');
    });

    it('is frozen (constants must not mutate at runtime)', () => {
      expect(Object.isFrozen(GENRE_HUE)).toBe(true);
    });
  });
});
