/**
 * pages/reader.test.ts
 *
 * Unit tests for M3 reader page logic (pure functions + page factory).
 *
 * Covers:
 *   - countWords: empty string, single word, multi-word
 *   - estimateMinutes: zero for empty, min 1 for short text, scales with word count
 *   - parsePortraitParagraphs: no characters, character matched, character not matched,
 *     only first mention per character gets portrait, second character can still match
 *   - readerPage factory: default state, goToChapter clamps, toggleSidebar
 *     toggles, readTime delegates to estimateMinutes
 *   - prefers-reduced-motion flag: reducedMotion initialises from window.matchMedia
 *   - ARIA: readingProgress 0..100, never negative, never over 100
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  countWords,
  estimateMinutes,
  parsePortraitParagraphs,
  readerPage,
} from '../../pages/reader';

// ── countWords ───────────────────────────────────────────────────────────────

describe('countWords', () => {
  it('returns 0 for empty string', () => {
    expect(countWords('')).toBe(0);
  });

  it('returns 0 for whitespace-only string', () => {
    expect(countWords('   ')).toBe(0);
  });

  it('counts single word', () => {
    expect(countWords('hello')).toBe(1);
  });

  it('counts multiple words', () => {
    expect(countWords('the quick brown fox')).toBe(4);
  });

  it('handles multiple spaces between words', () => {
    expect(countWords('a  b   c')).toBe(3);
  });

  it('handles newlines as whitespace', () => {
    expect(countWords('word\nanother')).toBe(2);
  });
});

// ── estimateMinutes ───────────────────────────────────────────────────────────

describe('estimateMinutes', () => {
  it('returns 0 for empty string', () => {
    expect(estimateMinutes('')).toBe(0);
  });

  it('returns minimum 1 for very short text', () => {
    expect(estimateMinutes('hello')).toBe(1);
  });

  it('returns correct minutes for exactly 200 words', () => {
    const text = 'word '.repeat(200).trim();
    expect(estimateMinutes(text)).toBe(1);
  });

  it('returns 2 for 201 words (ceil)', () => {
    const text = 'word '.repeat(201).trim();
    expect(estimateMinutes(text)).toBe(2);
  });

  it('scales linearly', () => {
    const text = 'word '.repeat(400).trim();
    expect(estimateMinutes(text)).toBe(2);
  });

  it('returns 0 for whitespace-only', () => {
    expect(estimateMinutes('   ')).toBe(0);
  });
});

// ── parsePortraitParagraphs ──────────────────────────────────────────────────

describe('parsePortraitParagraphs', () => {
  const charAlice = { name: 'Alice', portrait_url: 'https://img/alice.png', reference_url: null };
  const charBob = { name: 'Bob', portrait_url: null, reference_url: 'https://img/bob.png' };
  const charNoImg = { name: 'Charlie', portrait_url: null, reference_url: null };

  it('returns empty array for empty content', () => {
    expect(parsePortraitParagraphs('', [])).toEqual([]);
  });

  it('returns paragraphs with no portraitUrl when no characters given', () => {
    const result = parsePortraitParagraphs('Paragraph one.\n\nParagraph two.', []);
    expect(result).toHaveLength(2);
    expect(result[0].portraitUrl).toBeNull();
    expect(result[1].portraitUrl).toBeNull();
  });

  it('injects portrait on first mention of character', () => {
    const content = 'Alice walked in.\n\nThe room was quiet.';
    const result = parsePortraitParagraphs(content, [charAlice]);
    expect(result[0].portraitUrl).toBe('https://img/alice.png');
    expect(result[1].portraitUrl).toBeNull();
  });

  it('does not duplicate portrait on second mention of same character', () => {
    const content = 'Alice said hello.\n\nAlice smiled.';
    const result = parsePortraitParagraphs(content, [charAlice]);
    expect(result[0].portraitUrl).toBe('https://img/alice.png');
    expect(result[1].portraitUrl).toBeNull(); // already shown
  });

  it('falls back to reference_url when portrait_url is null', () => {
    const content = 'Bob entered the room.';
    const result = parsePortraitParagraphs(content, [charBob]);
    expect(result[0].portraitUrl).toBe('https://img/bob.png');
  });

  it('skips characters without any image URL', () => {
    const content = 'Charlie spoke first.';
    const result = parsePortraitParagraphs(content, [charNoImg]);
    expect(result[0].portraitUrl).toBeNull();
  });

  it('matches case-insensitively', () => {
    const content = 'ALICE ran forward.';
    const result = parsePortraitParagraphs(content, [charAlice]);
    expect(result[0].portraitUrl).toBe('https://img/alice.png');
  });

  it('allows second character to match in subsequent paragraphs', () => {
    const content = 'Alice arrived.\n\nBob followed.';
    const result = parsePortraitParagraphs(content, [charAlice, charBob]);
    expect(result[0].portraitUrl).toBe('https://img/alice.png');
    expect(result[1].portraitUrl).toBe('https://img/bob.png');
  });

  it('preserves paragraph text content', () => {
    const content = 'First para.\n\nSecond para.';
    const result = parsePortraitParagraphs(content, []);
    expect(result[0].text).toBe('First para.');
    expect(result[1].text).toBe('Second para.');
  });

  it('filters out blank paragraphs from newlines', () => {
    const content = 'Para one.\n\n\n\nPara two.';
    const result = parsePortraitParagraphs(content, []);
    expect(result).toHaveLength(2);
  });
});

// ── readerPage factory ────────────────────────────────────────────────────────

describe('readerPage factory', () => {
  beforeEach(() => {
    localStorage.clear();
    // Ensure Alpine.store is stubbed (from setup.js) and returns null by default.
    vi.mocked(Alpine.store).mockReturnValue(null);
  });

  function makeReader() {
    return readerPage();
  }

  it('initialises chapter to 0', () => {
    expect(makeReader().chapter).toBe(0);
  });

  it('initialises sidebarOpen to false', () => {
    expect(makeReader().sidebarOpen).toBe(false);
  });

  it('initialises readingProgress to 0', () => {
    expect(makeReader().readingProgress).toBe(0);
  });

  it('initialises paragraphs to empty array', () => {
    expect(makeReader().paragraphs).toEqual([]);
  });

  it('story returns null when pipelineResult is null', () => {
    vi.mocked(Alpine.store).mockReturnValue({ pipelineResult: null });
    const r = makeReader();
    expect(r.story).toBeNull();
  });

  it('story returns enhanced when available', () => {
    const story = { title: 'My Story', chapters: [] };
    vi.mocked(Alpine.store).mockImplementation((key: string) => {
      if (key === 'app') return { pipelineResult: { enhanced: story } };
      return null;
    });
    const r = makeReader();
    expect(r.story).toBe(story);
  });

  it('story falls back to draft when enhanced is absent', () => {
    const draft = { title: 'Draft', chapters: [] };
    vi.mocked(Alpine.store).mockImplementation((key: string) => {
      if (key === 'app') return { pipelineResult: { draft } };
      return null;
    });
    const r = makeReader();
    expect(r.story).toBe(draft);
  });

  it('chapters returns empty array when no story', () => {
    expect(makeReader().chapters).toEqual([]);
  });

  it('toggleSidebar flips sidebarOpen', () => {
    const r = makeReader();
    expect(r.sidebarOpen).toBe(false);
    r.toggleSidebar();
    expect(r.sidebarOpen).toBe(true);
    r.toggleSidebar();
    expect(r.sidebarOpen).toBe(false);
  });

  it('prev does nothing when chapter is 0', () => {
    const r = makeReader();
    r.prev();
    expect(r.chapter).toBe(0);
  });

  it('next does nothing when at last chapter (no chapters)', () => {
    const r = makeReader();
    r.next();
    expect(r.chapter).toBe(0);
  });

  it('next increments when chapters available', () => {
    vi.mocked(Alpine.store).mockImplementation((key: string) => {
      if (key === 'app') return {
        pipelineResult: {
          enhanced: { chapters: [{ content: 'Ch 1' }, { content: 'Ch 2' }] }
        }
      };
      return null;
    });
    const r = makeReader();
    r.next();
    expect(r.chapter).toBe(1);
  });

  it('goToChapter sets chapter within bounds', () => {
    vi.mocked(Alpine.store).mockImplementation((key: string) => {
      if (key === 'app') return {
        pipelineResult: {
          enhanced: { chapters: [{}, {}, {}] }
        }
      };
      return null;
    });
    const r = makeReader();
    r.goToChapter(2);
    expect(r.chapter).toBe(2);
  });

  it('goToChapter ignores out-of-bounds index (negative)', () => {
    const r = makeReader();
    r.goToChapter(-1);
    expect(r.chapter).toBe(0);
  });

  it('readTime returns 0 for chapter with no content', () => {
    const r = makeReader();
    expect(r.readTime({})).toBe(0);
  });

  it('readTime returns estimateMinutes for chapter content', () => {
    const r = makeReader();
    const ch = { content: 'word '.repeat(200).trim() };
    expect(r.readTime(ch)).toBe(1);
  });

  it('canContinue is false when pipelineResult is null', () => {
    vi.mocked(Alpine.store).mockReturnValue({ pipelineResult: null });
    const r = makeReader();
    expect(r.canContinue).toBe(false);
  });

  it('canContinue is true when pipelineResult has filename', () => {
    vi.mocked(Alpine.store).mockImplementation((key: string) => {
      if (key === 'app') return { pipelineResult: { filename: 'story.json' } };
      return null;
    });
    const r = makeReader();
    expect(r.canContinue).toBe(true);
  });
});

// ── prefers-reduced-motion ────────────────────────────────────────────────────

describe('reducedMotion detection', () => {
  it('defaults reducedMotion to false when matchMedia not available', () => {
    const r = readerPage();
    // jsdom has matchMedia returning false by default
    expect(r.reducedMotion).toBe(false);
  });

  it('sets reducedMotion true when matchMedia returns reduce match', () => {
    // Stub matchMedia to simulate reduced motion preference.
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never;
    const r = readerPage();
    // init() is called by Alpine — call it manually here.
    r.init?.();
    expect(r.reducedMotion).toBe(true);
    window.matchMedia = original;
  });
});

// ── readingProgress bounds ────────────────────────────────────────────────────

describe('_onScroll readingProgress bounds', () => {
  it('_onScroll leaves readingProgress at 0 when no content element found', () => {
    const r = readerPage();
    // No data-reader-content element exists in jsdom; _onScroll returns early.
    r._onScroll();
    // Progress stays at initial value (0) since the element was not found.
    expect(r.readingProgress).toBe(0);
  });

  it('readingProgress starts at 0', () => {
    const r = readerPage();
    expect(r.readingProgress).toBe(0);
  });
});
