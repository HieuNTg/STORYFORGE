/**
 * reader store — Forge UI typography + bookmark state for the Reader surface.
 *
 * Singleton store registered as `$store.reader` (Forge UI shipped on, STORYFORGE_FORGE_UI
 * is on. Pure presenter state — every field is hydrated from localStorage on
 * construction, and every setter persists back to localStorage immediately.
 *
 * Consumers:
 *   - Library reading-view template (font/line-height/theme controls)
 *   - reader.ts page (when present, M3 d4)
 *
 * Persistence keys (namespaced per plan §4.6):
 *   - forge_reader_font_size      number, px, clamped 12..32
 *   - forge_reader_line_height    number, 1.4..2.4 step 0.1
 *   - forge_reader_font_family    'serif' | 'sans' | 'mono'
 *   - forge_reader_theme          'day' | 'sepia' | 'night'
 *   - forge_reader_column         'narrow' | 'normal' | 'wide'
 *   - forge_reader_bookmarks      JSON Record<storyPath, { chapter:number; position?:number }>
 */

export type ReaderTheme = 'day' | 'sepia' | 'night';
export type ReaderFontFamily = 'serif' | 'sans' | 'mono';
export type ReaderColumn = 'narrow' | 'normal' | 'wide';

export interface ReaderBookmark {
  chapter: number;
  position?: number;
  updatedAt: number;
}

export interface ReaderStore {
  fontSize: number;
  lineHeight: number;
  fontFamily: ReaderFontFamily;
  theme: ReaderTheme;
  column: ReaderColumn;
  bookmarks: Record<string, ReaderBookmark>;

  setFontSize(v: number): void;
  bumpFontSize(delta: number): void;
  setLineHeight(v: number): void;
  setFontFamily(v: ReaderFontFamily): void;
  setTheme(v: ReaderTheme): void;
  cycleTheme(): void;
  setColumn(v: ReaderColumn): void;
  saveBookmark(storyPath: string, chapter: number, position?: number): void;
  getBookmark(storyPath: string): ReaderBookmark | null;
  clearBookmark(storyPath: string): void;
  reset(): void;

  /** Tailwind-class-style font-family value for `style="font-family:..."`. */
  readonly fontFamilyCss: string;
}

const FONT_SIZE_MIN = 12;
const FONT_SIZE_MAX = 32;
const LINE_HEIGHT_MIN = 1.4;
const LINE_HEIGHT_MAX = 2.4;
const THEMES: ReadonlyArray<ReaderTheme> = ['day', 'sepia', 'night'];
const FONT_FAMILIES: ReadonlyArray<ReaderFontFamily> = ['serif', 'sans', 'mono'];
const COLUMNS: ReadonlyArray<ReaderColumn> = ['narrow', 'normal', 'wide'];

const KEY_FONT_SIZE = 'forge_reader_font_size';
const KEY_LINE_HEIGHT = 'forge_reader_line_height';
const KEY_FONT_FAMILY = 'forge_reader_font_family';
const KEY_THEME = 'forge_reader_theme';
const KEY_COLUMN = 'forge_reader_column';
const KEY_BOOKMARKS = 'forge_reader_bookmarks';

/** Legacy localStorage key written by the embedded Library reader (Alpine local). */
const LEGACY_FONT_KEY = 'storyforge_reader_font_size';

const DEFAULTS = Object.freeze({
  fontSize: 18,
  lineHeight: 1.9,
  fontFamily: 'serif' as ReaderFontFamily,
  theme: 'day' as ReaderTheme,
  column: 'normal' as ReaderColumn,
});

function clampNumber(v: unknown, lo: number, hi: number, fallback: number): number {
  if (v === null || v === undefined || v === '') return fallback;
  const n = typeof v === 'number' ? v : Number(v);
  if (!Number.isFinite(n)) return fallback;
  if (n < lo) return lo;
  if (n > hi) return hi;
  return n;
}

function pickEnum<T extends string>(v: unknown, allowed: ReadonlyArray<T>, fallback: T): T {
  return typeof v === 'string' && (allowed as ReadonlyArray<string>).includes(v) ? (v as T) : fallback;
}

function safeRead(key: string): string | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage.getItem(key) : null;
  } catch {
    return null;
  }
}

function safeWrite(key: string, value: string): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(key, value);
  } catch {
    /* quota / private-mode — silent */
  }
}

function safeRemove(key: string): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

function loadBookmarks(): Record<string, ReaderBookmark> {
  const raw = safeRead(KEY_BOOKMARKS);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object') return {};
    const out: Record<string, ReaderBookmark> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (!v || typeof v !== 'object') continue;
      const entry = v as { chapter?: unknown; position?: unknown; updatedAt?: unknown };
      const chapter = typeof entry.chapter === 'number' && Number.isFinite(entry.chapter)
        ? Math.max(0, Math.floor(entry.chapter))
        : null;
      if (chapter === null) continue;
      const bookmark: ReaderBookmark = {
        chapter,
        updatedAt: typeof entry.updatedAt === 'number' ? entry.updatedAt : Date.now(),
      };
      if (typeof entry.position === 'number' && Number.isFinite(entry.position)) {
        bookmark.position = Math.max(0, entry.position);
      }
      out[k] = bookmark;
    }
    return out;
  } catch {
    return {};
  }
}

function fontFamilyCss(value: ReaderFontFamily): string {
  switch (value) {
    case 'sans':
      return 'system-ui, -apple-system, "Segoe UI", "Inter", sans-serif';
    case 'mono':
      return 'ui-monospace, "Cascadia Code", "JetBrains Mono", "Fira Code", monospace';
    case 'serif':
    default:
      return '"Iowan Old Style", "Charter", "Source Serif Pro", Georgia, serif';
  }
}

export function createReaderStore(): ReaderStore {
  // Migration shim: prefer namespaced key, fall back to legacy key for 1 sprint.
  const legacyFont = safeRead(LEGACY_FONT_KEY);
  const initialFont = clampNumber(
    safeRead(KEY_FONT_SIZE) ?? legacyFont,
    FONT_SIZE_MIN,
    FONT_SIZE_MAX,
    DEFAULTS.fontSize,
  );

  const store: ReaderStore = {
    fontSize: initialFont,
    lineHeight: clampNumber(safeRead(KEY_LINE_HEIGHT), LINE_HEIGHT_MIN, LINE_HEIGHT_MAX, DEFAULTS.lineHeight),
    fontFamily: pickEnum(safeRead(KEY_FONT_FAMILY), FONT_FAMILIES, DEFAULTS.fontFamily),
    theme: pickEnum(safeRead(KEY_THEME), THEMES, DEFAULTS.theme),
    column: pickEnum(safeRead(KEY_COLUMN), COLUMNS, DEFAULTS.column),
    bookmarks: loadBookmarks(),

    get fontFamilyCss(): string {
      return fontFamilyCss(this.fontFamily);
    },

    setFontSize(v: number): void {
      this.fontSize = clampNumber(v, FONT_SIZE_MIN, FONT_SIZE_MAX, DEFAULTS.fontSize);
      safeWrite(KEY_FONT_SIZE, String(this.fontSize));
    },
    bumpFontSize(delta: number): void {
      this.setFontSize(this.fontSize + delta);
    },
    setLineHeight(v: number): void {
      // Round to 0.1 step for stable storage / button-pair UX.
      const rounded = Math.round(v * 10) / 10;
      this.lineHeight = clampNumber(rounded, LINE_HEIGHT_MIN, LINE_HEIGHT_MAX, DEFAULTS.lineHeight);
      safeWrite(KEY_LINE_HEIGHT, String(this.lineHeight));
    },
    setFontFamily(v: ReaderFontFamily): void {
      this.fontFamily = pickEnum(v, FONT_FAMILIES, DEFAULTS.fontFamily);
      safeWrite(KEY_FONT_FAMILY, this.fontFamily);
    },
    setTheme(v: ReaderTheme): void {
      this.theme = pickEnum(v, THEMES, DEFAULTS.theme);
      safeWrite(KEY_THEME, this.theme);
    },
    cycleTheme(): void {
      const idx = THEMES.indexOf(this.theme);
      const next = THEMES[(idx + 1) % THEMES.length] ?? DEFAULTS.theme;
      this.setTheme(next);
    },
    setColumn(v: ReaderColumn): void {
      this.column = pickEnum(v, COLUMNS, DEFAULTS.column);
      safeWrite(KEY_COLUMN, this.column);
    },
    saveBookmark(storyPath: string, chapter: number, position?: number): void {
      if (!storyPath) return;
      const safeChapter = Math.max(0, Math.floor(Number(chapter) || 0));
      const bookmark: ReaderBookmark = { chapter: safeChapter, updatedAt: Date.now() };
      if (typeof position === 'number' && Number.isFinite(position)) {
        bookmark.position = Math.max(0, position);
      }
      this.bookmarks[storyPath] = bookmark;
      safeWrite(KEY_BOOKMARKS, JSON.stringify(this.bookmarks));
    },
    getBookmark(storyPath: string): ReaderBookmark | null {
      return this.bookmarks[storyPath] ?? null;
    },
    clearBookmark(storyPath: string): void {
      if (!(storyPath in this.bookmarks)) return;
      delete this.bookmarks[storyPath];
      safeWrite(KEY_BOOKMARKS, JSON.stringify(this.bookmarks));
    },
    reset(): void {
      this.fontSize = DEFAULTS.fontSize;
      this.lineHeight = DEFAULTS.lineHeight;
      this.fontFamily = DEFAULTS.fontFamily;
      this.theme = DEFAULTS.theme;
      this.column = DEFAULTS.column;
      this.bookmarks = {};
      safeRemove(KEY_FONT_SIZE);
      safeRemove(KEY_LINE_HEIGHT);
      safeRemove(KEY_FONT_FAMILY);
      safeRemove(KEY_THEME);
      safeRemove(KEY_COLUMN);
      safeRemove(KEY_BOOKMARKS);
    },
  };

  return store;
}
