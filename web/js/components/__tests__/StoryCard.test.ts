/**
 * Tests for StoryCard Alpine.data factory.
 *
 * Covers:
 *   - Defaults + prop overrides
 *   - progress / progressPct computation
 *   - showProgress visibility rule
 *   - ariaLabel composition by status & chapter count
 *   - State setters (status, hovered)
 *   - Dispatch behaviour for open/continue/branch/delete
 */

import { describe, it, expect, vi } from 'vitest';
import { storyCard } from '../StoryCard';

describe('storyCard', () => {
  it('uses sane defaults when only required props are supplied', () => {
    const c = storyCard({ storyId: 's1', title: 'A', genreId: 'tien-hiep' });
    expect(c.storyId).toBe('s1');
    expect(c.title).toBe('A');
    expect(c.genreId).toBe('tien-hiep');
    expect(c.hue).toBe('');
    expect(c.coverSrc).toBe('');
    expect(c.chapters).toBe(0);
    expect(c.chaptersDone).toBe(0);
    expect(c.status).toBe('idle');
    expect(c.mode).toBe('grid');
    expect(c.hovered).toBe(false);
  });

  it('respects every prop when supplied', () => {
    const c = storyCard({
      storyId: 's2',
      title: 'Đại Đạo',
      genreId: 'tien-hiep',
      hue: '#10B981',
      coverSrc: '/img/c.png',
      chapters: 10,
      chaptersDone: 4,
      status: 'generating',
      mode: 'list',
    });
    expect(c.hue).toBe('#10B981');
    expect(c.coverSrc).toBe('/img/c.png');
    expect(c.chapters).toBe(10);
    expect(c.chaptersDone).toBe(4);
    expect(c.status).toBe('generating');
    expect(c.mode).toBe('list');
  });

  it('clamps chaptersDone into [0, chapters]', () => {
    const over = storyCard({ storyId: 's', title: 'T', genreId: 'g', chapters: 5, chaptersDone: 99 });
    expect(over.chaptersDone).toBe(5);
    const neg = storyCard({ storyId: 's', title: 'T', genreId: 'g', chapters: 5, chaptersDone: -3 });
    expect(neg.chaptersDone).toBe(0);
  });

  it('floors fractional chapter counts and rejects NaN', () => {
    const c = storyCard({ storyId: 's', title: 'T', genreId: 'g', chapters: 7.8, chaptersDone: 2.4 });
    expect(c.chapters).toBe(7);
    expect(c.chaptersDone).toBe(2);
    const nan = storyCard({
      storyId: 's', title: 'T', genreId: 'g',
      chapters: Number.NaN, chaptersDone: Number.NaN,
    });
    expect(nan.chapters).toBe(0);
    expect(nan.chaptersDone).toBe(0);
  });

  describe('progress', () => {
    it('returns 0 when no chapters defined', () => {
      const c = storyCard({ storyId: 's', title: 'T', genreId: 'g' });
      expect(c.progress).toBe(0);
      expect(c.progressPct).toBe(0);
    });

    it('returns the chaptersDone / chapters ratio', () => {
      const c = storyCard({
        storyId: 's', title: 'T', genreId: 'g',
        chapters: 4, chaptersDone: 1,
      });
      expect(c.progress).toBe(0.25);
      expect(c.progressPct).toBe(25);
    });

    it('rounds progressPct to an integer', () => {
      const c = storyCard({
        storyId: 's', title: 'T', genreId: 'g',
        chapters: 3, chaptersDone: 1,
      });
      expect(c.progressPct).toBe(33);
    });
  });

  describe('showProgress', () => {
    it('is true only when status==="generating" AND chapters > 0', () => {
      const gen = storyCard({
        storyId: 's', title: 'T', genreId: 'g',
        chapters: 5, chaptersDone: 1, status: 'generating',
      });
      expect(gen.showProgress).toBe(true);

      const empty = storyCard({
        storyId: 's', title: 'T', genreId: 'g',
        chapters: 0, status: 'generating',
      });
      expect(empty.showProgress).toBe(false);

      const done = storyCard({
        storyId: 's', title: 'T', genreId: 'g',
        chapters: 5, status: 'done',
      });
      expect(done.showProgress).toBe(false);
    });
  });

  describe('ariaLabel', () => {
    it('omits chapter count when zero', () => {
      const c = storyCard({ storyId: 's', title: 'Quest', genreId: 'tien-hiep' });
      expect(c.ariaLabel).toBe('Quest, tien-hiep, ready');
    });

    it('includes singular form for exactly one chapter', () => {
      const c = storyCard({
        storyId: 's', title: 'Quest', genreId: 'g', chapters: 1, status: 'done',
      });
      expect(c.ariaLabel).toBe('Quest, g, 1 chapter, complete');
    });

    it('includes plural chapter count and status', () => {
      const c = storyCard({
        storyId: 's', title: 'Quest', genreId: 'g',
        chapters: 12, status: 'generating',
      });
      expect(c.ariaLabel).toBe('Quest, g, 12 chapters, generating');
    });
  });

  describe('setters', () => {
    it('setStatus mutates state', () => {
      const c = storyCard({ storyId: 's', title: 'T', genreId: 'g' });
      c.setStatus('error');
      expect(c.status).toBe('error');
    });

    it('setHovered mutates hover flag', () => {
      const c = storyCard({ storyId: 's', title: 'T', genreId: 'g' });
      c.setHovered(true);
      expect(c.hovered).toBe(true);
    });
  });

  describe('dispatchers', () => {
    it('handleOpen dispatches sf:story-open with the story id', () => {
      const c = storyCard({ storyId: 's42', title: 'T', genreId: 'g' });
      const dispatch = vi.fn();
      Object.assign(c, { $dispatch: dispatch });
      c.handleOpen();
      expect(dispatch).toHaveBeenCalledWith('sf:story-open', { id: 's42' });
    });

    it('handleContinue dispatches sf:story-continue and stops propagation', () => {
      const c = storyCard({ storyId: 's42', title: 'T', genreId: 'g' });
      const dispatch = vi.fn();
      const event = { stopPropagation: vi.fn() } as unknown as Event;
      Object.assign(c, { $dispatch: dispatch });
      c.handleContinue(event);
      expect(dispatch).toHaveBeenCalledWith('sf:story-continue', { id: 's42' });
      expect((event as any).stopPropagation).toHaveBeenCalled();
    });

    it('handleBranch and handleDelete dispatch their respective events', () => {
      const c = storyCard({ storyId: 's7', title: 'T', genreId: 'g' });
      const dispatch = vi.fn();
      Object.assign(c, { $dispatch: dispatch });
      c.handleBranch();
      c.handleDelete();
      expect(dispatch).toHaveBeenCalledWith('sf:story-branch', { id: 's7' });
      expect(dispatch).toHaveBeenCalledWith('sf:story-delete', { id: 's7' });
    });

    it('dispatch handlers are no-ops when $dispatch is unbound', () => {
      const c = storyCard({ storyId: 's', title: 'T', genreId: 'g' });
      expect(() => c.handleOpen()).not.toThrow();
      expect(() => c.handleContinue()).not.toThrow();
      expect(() => c.handleBranch()).not.toThrow();
      expect(() => c.handleDelete()).not.toThrow();
    });
  });
});
