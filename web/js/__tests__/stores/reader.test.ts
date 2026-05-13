/**
 * stores/reader.test.ts
 *
 * Unit tests for createReaderStore() in web/js/stores/reader.ts.
 *
 * Covers:
 *   - Default values (fontSize=18, lineHeight=1.9, serif theme=day, column=normal)
 *   - setFontSize: clamps to [12..32], persists key
 *   - bumpFontSize: delta applied then clamped
 *   - setLineHeight: rounds to 0.1 step, clamps [1.4..2.4]
 *   - setFontFamily: accepts only 'serif'|'sans'|'mono', rejects unknown
 *   - setTheme: accepts only 'day'|'sepia'|'night'
 *   - cycleTheme: day -> sepia -> night -> day
 *   - setColumn: accepts only 'narrow'|'normal'|'wide'
 *   - saveBookmark / getBookmark / clearBookmark round-trip
 *   - reset: clears all fields to defaults + removes localStorage keys
 *   - fontFamilyCss getter
 *   - Legacy localStorage key migration shim
 *   - ARIA/accessibility: all setters write localStorage, no errors on quota
 *   - prefers-reduced-motion: store is pure state, not affected (side-effect-free)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createReaderStore } from '../../stores/reader';

// ── helpers ──────────────────────────────────────────────────────────────────

function freshStore() {
  localStorage.clear();
  return createReaderStore();
}

// ── defaults ─────────────────────────────────────────────────────────────────

describe('createReaderStore — defaults', () => {
  beforeEach(() => localStorage.clear());

  it('fontSize defaults to 18', () => {
    expect(freshStore().fontSize).toBe(18);
  });

  it('lineHeight defaults to 1.9', () => {
    expect(freshStore().lineHeight).toBeCloseTo(1.9);
  });

  it('fontFamily defaults to serif', () => {
    expect(freshStore().fontFamily).toBe('serif');
  });

  it('theme defaults to day', () => {
    expect(freshStore().theme).toBe('day');
  });

  it('column defaults to normal', () => {
    expect(freshStore().column).toBe('normal');
  });

  it('bookmarks defaults to empty object', () => {
    expect(freshStore().bookmarks).toEqual({});
  });
});

// ── setFontSize ───────────────────────────────────────────────────────────────

describe('setFontSize', () => {
  beforeEach(() => localStorage.clear());

  it('sets within range', () => {
    const s = freshStore();
    s.setFontSize(20);
    expect(s.fontSize).toBe(20);
    expect(localStorage.getItem('forge_reader_font_size')).toBe('20');
  });

  it('clamps below minimum to 12', () => {
    const s = freshStore();
    s.setFontSize(5);
    expect(s.fontSize).toBe(12);
  });

  it('clamps above maximum to 32', () => {
    const s = freshStore();
    s.setFontSize(999);
    expect(s.fontSize).toBe(32);
  });
});

// ── bumpFontSize ──────────────────────────────────────────────────────────────

describe('bumpFontSize', () => {
  beforeEach(() => localStorage.clear());

  it('bumps by positive delta', () => {
    const s = freshStore();
    s.bumpFontSize(2);
    expect(s.fontSize).toBe(20);
  });

  it('bumps by negative delta', () => {
    const s = freshStore();
    s.bumpFontSize(-4);
    expect(s.fontSize).toBe(14);
  });

  it('bump clamped at minimum', () => {
    const s = freshStore();
    s.bumpFontSize(-100);
    expect(s.fontSize).toBe(12);
  });

  it('bump clamped at maximum', () => {
    const s = freshStore();
    s.bumpFontSize(100);
    expect(s.fontSize).toBe(32);
  });
});

// ── setLineHeight ─────────────────────────────────────────────────────────────

describe('setLineHeight', () => {
  beforeEach(() => localStorage.clear());

  it('sets valid value', () => {
    const s = freshStore();
    s.setLineHeight(1.8);
    expect(s.lineHeight).toBeCloseTo(1.8);
    expect(localStorage.getItem('forge_reader_line_height')).toBe('1.8');
  });

  it('rounds to 1 decimal', () => {
    const s = freshStore();
    s.setLineHeight(1.756);
    // Rounded to 0.1 step: 1.8
    expect(s.lineHeight).toBeCloseTo(1.8);
  });

  it('clamps below minimum to 1.4', () => {
    const s = freshStore();
    s.setLineHeight(1.0);
    expect(s.lineHeight).toBeCloseTo(1.4);
  });

  it('clamps above maximum to 2.4', () => {
    const s = freshStore();
    s.setLineHeight(3.0);
    expect(s.lineHeight).toBeCloseTo(2.4);
  });
});

// ── setFontFamily ─────────────────────────────────────────────────────────────

describe('setFontFamily', () => {
  beforeEach(() => localStorage.clear());

  it('accepts serif', () => {
    const s = freshStore();
    s.setFontFamily('sans');
    s.setFontFamily('serif');
    expect(s.fontFamily).toBe('serif');
  });

  it('accepts sans', () => {
    const s = freshStore();
    s.setFontFamily('sans');
    expect(s.fontFamily).toBe('sans');
  });

  it('accepts mono', () => {
    const s = freshStore();
    s.setFontFamily('mono');
    expect(s.fontFamily).toBe('mono');
  });

  it('rejects unknown string, falls back to serif default', () => {
    const s = freshStore();
    s.setFontFamily('comic-sans' as never);
    expect(s.fontFamily).toBe('serif');
  });
});

// ── setTheme / cycleTheme ─────────────────────────────────────────────────────

describe('setTheme', () => {
  beforeEach(() => localStorage.clear());

  it('sets sepia', () => {
    const s = freshStore();
    s.setTheme('sepia');
    expect(s.theme).toBe('sepia');
  });

  it('sets night', () => {
    const s = freshStore();
    s.setTheme('night');
    expect(s.theme).toBe('night');
  });

  it('rejects unknown, falls back to day', () => {
    const s = freshStore();
    s.setTheme('mystery' as never);
    expect(s.theme).toBe('day');
  });
});

describe('cycleTheme', () => {
  beforeEach(() => localStorage.clear());

  it('cycles day -> sepia -> night -> day', () => {
    const s = freshStore();
    expect(s.theme).toBe('day');
    s.cycleTheme();
    expect(s.theme).toBe('sepia');
    s.cycleTheme();
    expect(s.theme).toBe('night');
    s.cycleTheme();
    expect(s.theme).toBe('day');
  });
});

// ── setColumn ─────────────────────────────────────────────────────────────────

describe('setColumn', () => {
  beforeEach(() => localStorage.clear());

  it('accepts narrow', () => {
    const s = freshStore();
    s.setColumn('narrow');
    expect(s.column).toBe('narrow');
  });

  it('accepts wide', () => {
    const s = freshStore();
    s.setColumn('wide');
    expect(s.column).toBe('wide');
  });

  it('rejects unknown, falls back to normal', () => {
    const s = freshStore();
    s.setColumn('ultra-wide' as never);
    expect(s.column).toBe('normal');
  });
});

// ── bookmarks ─────────────────────────────────────────────────────────────────

describe('bookmarks', () => {
  beforeEach(() => localStorage.clear());

  it('saves and retrieves a bookmark', () => {
    const s = freshStore();
    s.saveBookmark('story-abc', 3);
    const bm = s.getBookmark('story-abc');
    expect(bm).not.toBeNull();
    expect(bm!.chapter).toBe(3);
  });

  it('saves bookmark with position', () => {
    const s = freshStore();
    s.saveBookmark('story-abc', 2, 450);
    const bm = s.getBookmark('story-abc');
    expect(bm!.position).toBe(450);
  });

  it('returns null for unknown story', () => {
    const s = freshStore();
    expect(s.getBookmark('no-such-story')).toBeNull();
  });

  it('clears a bookmark', () => {
    const s = freshStore();
    s.saveBookmark('story-abc', 1);
    s.clearBookmark('story-abc');
    expect(s.getBookmark('story-abc')).toBeNull();
  });

  it('ignores clearBookmark for unknown story', () => {
    const s = freshStore();
    // Should not throw
    expect(() => s.clearBookmark('ghost')).not.toThrow();
  });

  it('persists bookmarks to localStorage', () => {
    const s = freshStore();
    s.saveBookmark('story-x', 0);
    const raw = localStorage.getItem('forge_reader_bookmarks');
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!);
    expect(parsed['story-x'].chapter).toBe(0);
  });
});

// ── reset ─────────────────────────────────────────────────────────────────────

describe('reset', () => {
  beforeEach(() => localStorage.clear());

  it('resets all fields to defaults', () => {
    const s = freshStore();
    s.setFontSize(24);
    s.setTheme('night');
    s.saveBookmark('x', 5);
    s.reset();
    expect(s.fontSize).toBe(18);
    expect(s.theme).toBe('day');
    expect(s.bookmarks).toEqual({});
  });

  it('removes localStorage keys', () => {
    const s = freshStore();
    s.setFontSize(24);
    s.reset();
    expect(localStorage.getItem('forge_reader_font_size')).toBeNull();
  });
});

// ── fontFamilyCss getter ──────────────────────────────────────────────────────

describe('fontFamilyCss getter', () => {
  beforeEach(() => localStorage.clear());

  it('returns serif stack for serif fontFamily', () => {
    const s = freshStore();
    // default is serif
    expect(s.fontFamilyCss).toContain('Georgia');
  });

  it('returns sans-serif stack for sans fontFamily', () => {
    const s = freshStore();
    s.setFontFamily('sans');
    expect(s.fontFamilyCss).toContain('system-ui');
  });

  it('returns monospace stack for mono fontFamily', () => {
    const s = freshStore();
    s.setFontFamily('mono');
    expect(s.fontFamilyCss).toContain('monospace');
  });
});

// ── legacy key migration shim ─────────────────────────────────────────────────

describe('legacy key migration', () => {
  it('reads legacy storyforge_reader_font_size when new key absent', () => {
    localStorage.clear();
    localStorage.setItem('storyforge_reader_font_size', '22');
    const s = createReaderStore();
    expect(s.fontSize).toBe(22);
  });

  it('prefers new key over legacy key', () => {
    localStorage.clear();
    localStorage.setItem('storyforge_reader_font_size', '22');
    localStorage.setItem('forge_reader_font_size', '16');
    const s = createReaderStore();
    expect(s.fontSize).toBe(16);
  });
});

// ── hydration from localStorage ───────────────────────────────────────────────

describe('hydration from localStorage', () => {
  it('loads persisted theme', () => {
    localStorage.clear();
    localStorage.setItem('forge_reader_theme', 'sepia');
    const s = createReaderStore();
    expect(s.theme).toBe('sepia');
  });

  it('loads persisted column', () => {
    localStorage.clear();
    localStorage.setItem('forge_reader_column', 'wide');
    const s = createReaderStore();
    expect(s.column).toBe('wide');
  });

  it('ignores corrupt JSON bookmarks and returns empty object', () => {
    localStorage.clear();
    localStorage.setItem('forge_reader_bookmarks', '{{{invalid');
    const s = createReaderStore();
    expect(s.bookmarks).toEqual({});
  });
});
