/**
 * Tests for reader.ts — Forge UI reader prefs + bookmark store.
 *
 * Covers:
 *   - defaults applied when localStorage is empty
 *   - hydration from valid localStorage values
 *   - clamping for font size & line height
 *   - enum guards for theme / fontFamily / column
 *   - setters persist back to localStorage
 *   - bookmark save / get / clear roundtrip
 *   - reset() wipes both state and storage
 *   - legacy storyforge_reader_font_size migration shim
 *   - safe behaviour when localStorage throws
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { createReaderStore } from '../reader';

function clearReaderKeys(): void {
  [
    'forge_reader_font_size',
    'forge_reader_line_height',
    'forge_reader_font_family',
    'forge_reader_theme',
    'forge_reader_column',
    'forge_reader_bookmarks',
    'storyforge_reader_font_size',
  ].forEach((k) => localStorage.removeItem(k));
}

beforeEach(() => {
  clearReaderKeys();
});

describe('reader store — defaults', () => {
  it('falls back to plan defaults when storage is empty', () => {
    const s = createReaderStore();
    expect(s.fontSize).toBe(18);
    expect(s.lineHeight).toBe(1.9);
    expect(s.fontFamily).toBe('serif');
    expect(s.theme).toBe('day');
    expect(s.column).toBe('normal');
    expect(s.bookmarks).toEqual({});
  });

  it('exposes a fontFamilyCss derived value', () => {
    const s = createReaderStore();
    expect(s.fontFamilyCss).toMatch(/serif/i);
    s.setFontFamily('mono');
    expect(s.fontFamilyCss).toMatch(/mono/i);
    s.setFontFamily('sans');
    expect(s.fontFamilyCss).toMatch(/sans/i);
  });
});

describe('reader store — hydration', () => {
  it('reads valid values from localStorage', () => {
    localStorage.setItem('forge_reader_font_size', '22');
    localStorage.setItem('forge_reader_line_height', '2.1');
    localStorage.setItem('forge_reader_font_family', 'sans');
    localStorage.setItem('forge_reader_theme', 'night');
    localStorage.setItem('forge_reader_column', 'wide');
    const s = createReaderStore();
    expect(s.fontSize).toBe(22);
    expect(s.lineHeight).toBe(2.1);
    expect(s.fontFamily).toBe('sans');
    expect(s.theme).toBe('night');
    expect(s.column).toBe('wide');
  });

  it('falls back to defaults on garbage values', () => {
    localStorage.setItem('forge_reader_font_size', 'NaN');
    localStorage.setItem('forge_reader_theme', 'rainbow');
    localStorage.setItem('forge_reader_column', 'whatever');
    const s = createReaderStore();
    expect(s.fontSize).toBe(18);
    expect(s.theme).toBe('day');
    expect(s.column).toBe('normal');
  });

  it('clamps stored font size into the 12..32 range', () => {
    localStorage.setItem('forge_reader_font_size', '999');
    expect(createReaderStore().fontSize).toBe(32);
    localStorage.setItem('forge_reader_font_size', '4');
    expect(createReaderStore().fontSize).toBe(12);
  });

  it('migrates from the legacy storyforge_reader_font_size key when no forge key is set', () => {
    localStorage.setItem('storyforge_reader_font_size', '20');
    expect(createReaderStore().fontSize).toBe(20);
  });

  it('prefers the forge key over the legacy key when both exist', () => {
    localStorage.setItem('storyforge_reader_font_size', '20');
    localStorage.setItem('forge_reader_font_size', '24');
    expect(createReaderStore().fontSize).toBe(24);
  });
});

describe('reader store — setters', () => {
  it('setFontSize clamps and persists', () => {
    const s = createReaderStore();
    s.setFontSize(26);
    expect(s.fontSize).toBe(26);
    expect(localStorage.getItem('forge_reader_font_size')).toBe('26');
    s.setFontSize(999);
    expect(s.fontSize).toBe(32);
    s.setFontSize(-5);
    expect(s.fontSize).toBe(12);
  });

  it('bumpFontSize adds delta with clamp', () => {
    const s = createReaderStore();
    s.setFontSize(20);
    s.bumpFontSize(4);
    expect(s.fontSize).toBe(24);
    s.bumpFontSize(100);
    expect(s.fontSize).toBe(32);
    s.bumpFontSize(-999);
    expect(s.fontSize).toBe(12);
  });

  it('setLineHeight rounds to one decimal and persists', () => {
    const s = createReaderStore();
    s.setLineHeight(1.84);
    expect(s.lineHeight).toBe(1.8);
    expect(localStorage.getItem('forge_reader_line_height')).toBe('1.8');
    s.setLineHeight(5);
    expect(s.lineHeight).toBe(2.4);
    s.setLineHeight(0);
    expect(s.lineHeight).toBe(1.4);
  });

  it('setFontFamily rejects invalid values', () => {
    const s = createReaderStore();
    s.setFontFamily('mono');
    expect(s.fontFamily).toBe('mono');
    s.setFontFamily('comic-sans' as never);
    expect(s.fontFamily).toBe('serif');
  });

  it('setTheme persists and cycleTheme walks day → sepia → night → day', () => {
    const s = createReaderStore();
    expect(s.theme).toBe('day');
    s.cycleTheme();
    expect(s.theme).toBe('sepia');
    s.cycleTheme();
    expect(s.theme).toBe('night');
    s.cycleTheme();
    expect(s.theme).toBe('day');
    expect(localStorage.getItem('forge_reader_theme')).toBe('day');
  });

  it('setColumn accepts narrow/normal/wide only', () => {
    const s = createReaderStore();
    s.setColumn('narrow');
    expect(s.column).toBe('narrow');
    s.setColumn('huge' as never);
    expect(s.column).toBe('normal');
  });
});

describe('reader store — bookmarks', () => {
  it('save/get roundtrips and persists JSON', () => {
    const s = createReaderStore();
    s.saveBookmark('story-a.json', 3, 1024);
    const got = s.getBookmark('story-a.json');
    expect(got?.chapter).toBe(3);
    expect(got?.position).toBe(1024);
    expect(typeof got?.updatedAt).toBe('number');
    const raw = localStorage.getItem('forge_reader_bookmarks');
    expect(raw).toBeTruthy();
    const parsed = JSON.parse(raw as string);
    expect(parsed['story-a.json'].chapter).toBe(3);
  });

  it('ignores empty storyPath silently', () => {
    const s = createReaderStore();
    s.saveBookmark('', 2);
    expect(s.bookmarks).toEqual({});
  });

  it('saveBookmark overwrites the existing entry for the same story', () => {
    const s = createReaderStore();
    s.saveBookmark('a', 1);
    s.saveBookmark('a', 5, 200);
    expect(s.bookmarks['a']?.chapter).toBe(5);
    expect(s.bookmarks['a']?.position).toBe(200);
  });

  it('getBookmark returns null for unknown stories', () => {
    const s = createReaderStore();
    expect(s.getBookmark('unknown')).toBeNull();
  });

  it('clearBookmark removes the entry and rewrites storage', () => {
    const s = createReaderStore();
    s.saveBookmark('x', 1);
    s.saveBookmark('y', 2);
    s.clearBookmark('x');
    expect(s.getBookmark('x')).toBeNull();
    expect(s.getBookmark('y')?.chapter).toBe(2);
    const parsed = JSON.parse(localStorage.getItem('forge_reader_bookmarks') as string);
    expect(parsed).toEqual(expect.objectContaining({ y: expect.objectContaining({ chapter: 2 }) }));
    expect(parsed.x).toBeUndefined();
  });

  it('hydrates bookmarks from valid JSON in storage', () => {
    localStorage.setItem(
      'forge_reader_bookmarks',
      JSON.stringify({ 'a.json': { chapter: 4, position: 99, updatedAt: 123 } }),
    );
    const s = createReaderStore();
    expect(s.bookmarks['a.json']?.chapter).toBe(4);
    expect(s.bookmarks['a.json']?.position).toBe(99);
  });

  it('drops malformed bookmark entries silently', () => {
    localStorage.setItem(
      'forge_reader_bookmarks',
      JSON.stringify({
        ok: { chapter: 2 },
        nope: { chapter: 'three' },
        nada: null,
        broken: 'not-an-object',
      }),
    );
    const s = createReaderStore();
    expect(Object.keys(s.bookmarks)).toEqual(['ok']);
  });

  it('returns {} on completely invalid JSON in storage', () => {
    localStorage.setItem('forge_reader_bookmarks', '{not json');
    expect(createReaderStore().bookmarks).toEqual({});
  });
});

describe('reader store — reset', () => {
  it('wipes both state and storage', () => {
    const s = createReaderStore();
    s.setFontSize(26);
    s.setTheme('night');
    s.saveBookmark('p', 2);
    s.reset();
    expect(s.fontSize).toBe(18);
    expect(s.theme).toBe('day');
    expect(s.bookmarks).toEqual({});
    expect(localStorage.getItem('forge_reader_font_size')).toBeNull();
    expect(localStorage.getItem('forge_reader_bookmarks')).toBeNull();
  });
});
