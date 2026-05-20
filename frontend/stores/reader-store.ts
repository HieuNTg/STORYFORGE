"use client";

/**
 * reader-store — Reader prefs + bookmarks (Zustand + custom persist).
 *
 * Persistence parity with legacy `web/js/stores/reader.ts`:
 *   - Each field stored under its own localStorage key (NOT one combined JSON
 *     blob) so the legacy Alpine reader and the new React reader can share
 *     prefs during the cutover window (R2.2). Keys MUST match verbatim:
 *
 *       forge_reader_font_size      (number, 12..32)
 *       forge_reader_line_height    (number, 1.4..2.4)
 *       forge_reader_font_family    'serif' | 'sans' | 'mono'
 *       forge_reader_theme          'day' | 'sepia' | 'night'
 *       forge_reader_column         'narrow' | 'normal' | 'wide'
 *       forge_reader_bookmarks      JSON Record<storyPath, { chapter, position?, updatedAt }>
 *
 * Reader page also tracks `currentChapter` per spec; that one is NOT persisted
 * (it lives in nuqs `?chapter=` for shareability).
 */

import { create } from "zustand";

/**
 * Theme tokens — Phase 4 redesign expands to 4 cinematic surfaces:
 *   `midnight` — gold-on-dark cinematic default (new)
 *   `sepia`    — warm parchment (legacy compatible)
 *   `dark`     — neutral dark (legacy `night` migrates here)
 *   `light`    — clean light (legacy `day` migrates here)
 */
export type ReaderTheme = "midnight" | "sepia" | "dark" | "light";
export type ReaderFontFamily = "sans" | "serif" | "mono";
/**
 * Legacy column tokens — kept verbatim for `forge_reader_column` storage
 * parity (R2.2). UI components use Designer's `narrow|medium|wide`; the page
 * adapts via {@link columnToUi}/{@link columnFromUi}.
 */
export type ReaderColumn = "narrow" | "normal" | "wide";
export type ReaderColumnUi = "narrow" | "medium" | "wide";

export function columnToUi(c: ReaderColumn): ReaderColumnUi {
  return c === "normal" ? "medium" : c;
}
export function columnFromUi(c: ReaderColumnUi): ReaderColumn {
  return c === "medium" ? "normal" : c;
}

export interface ReaderBookmark {
  chapter: number;
  position?: number;
  updatedAt: number;
}

export interface ReaderState {
  fontSize: number;
  lineHeight: number;
  fontFamily: ReaderFontFamily;
  theme: ReaderTheme;
  column: ReaderColumn;
  bookmarks: Record<string, ReaderBookmark>;
  /** Hydration flag — `false` during first render on the client (SSR safe). */
  _hydrated: boolean;

  setFontSize(v: number): void;
  bumpFontSize(delta: number): void;
  setLineHeight(v: number): void;
  setFontFamily(v: ReaderFontFamily): void;
  setTheme(v: ReaderTheme): void;
  cycleTheme(): void;
  setColumn(v: ReaderColumn): void;
  saveBookmark(storyPath: string, chapter: number, position?: number): void;
  clearBookmark(storyPath: string): void;
  getBookmark(storyPath: string): ReaderBookmark | null;
  reset(): void;
  /** Re-read all keys from localStorage. Call once on first client render. */
  hydrate(): void;
}

const KEY_FONT_SIZE = "forge_reader_font_size";
const KEY_LINE_HEIGHT = "forge_reader_line_height";
const KEY_FONT_FAMILY = "forge_reader_font_family";
const KEY_THEME = "forge_reader_theme";
const KEY_COLUMN = "forge_reader_column";
const KEY_BOOKMARKS = "forge_reader_bookmarks";
const LEGACY_FONT_KEY = "storyforge_reader_font_size";

const FONT_SIZE_MIN = 12;
const FONT_SIZE_MAX = 32;
const LINE_HEIGHT_MIN = 1.4;
const LINE_HEIGHT_MAX = 2.4;
const THEMES: ReadonlyArray<ReaderTheme> = ["midnight", "sepia", "dark", "light"];
const LEGACY_THEME_MAP: Record<string, ReaderTheme> = {
  day: "light",
  night: "dark",
};
function migrateTheme(v: unknown): ReaderTheme | null {
  if (typeof v !== "string") return null;
  if ((THEMES as ReadonlyArray<string>).includes(v)) return v as ReaderTheme;
  return LEGACY_THEME_MAP[v] ?? null;
}
const FONT_FAMILIES: ReadonlyArray<ReaderFontFamily> = ["serif", "sans", "mono"];
const COLUMNS: ReadonlyArray<ReaderColumn> = ["narrow", "normal", "wide"];

const DEFAULTS = Object.freeze({
  fontSize: 16,
  lineHeight: 1.6,
  fontFamily: "sans" as ReaderFontFamily,
  theme: "midnight" as ReaderTheme,
  column: "normal" as ReaderColumn,
});

function safeRead(key: string): string | null {
  try {
    return typeof localStorage !== "undefined" ? localStorage.getItem(key) : null;
  } catch {
    return null;
  }
}
function safeWrite(key: string, value: string): void {
  try {
    if (typeof localStorage !== "undefined") localStorage.setItem(key, value);
  } catch {
    /* quota / private mode */
  }
}
function safeRemove(key: string): void {
  try {
    if (typeof localStorage !== "undefined") localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

function clampNumber(v: unknown, lo: number, hi: number, fallback: number): number {
  if (v === null || v === undefined || v === "") return fallback;
  const n = typeof v === "number" ? v : Number(v);
  if (!Number.isFinite(n)) return fallback;
  if (n < lo) return lo;
  if (n > hi) return hi;
  return n;
}

function pickEnum<T extends string>(v: unknown, allowed: ReadonlyArray<T>, fb: T): T {
  return typeof v === "string" && (allowed as ReadonlyArray<string>).includes(v) ? (v as T) : fb;
}

function loadBookmarks(): Record<string, ReaderBookmark> {
  const raw = safeRead(KEY_BOOKMARKS);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object") return {};
    const out: Record<string, ReaderBookmark> = {};
    for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
      if (!v || typeof v !== "object") continue;
      const e = v as { chapter?: unknown; position?: unknown; updatedAt?: unknown };
      const chapter =
        typeof e.chapter === "number" && Number.isFinite(e.chapter)
          ? Math.max(0, Math.floor(e.chapter))
          : null;
      if (chapter === null) continue;
      const entry: ReaderBookmark = {
        chapter,
        updatedAt: typeof e.updatedAt === "number" ? e.updatedAt : Date.now(),
      };
      if (typeof e.position === "number" && Number.isFinite(e.position)) {
        entry.position = Math.max(0, e.position);
      }
      out[k] = entry;
    }
    return out;
  } catch {
    return {};
  }
}

function readInitial(): Omit<ReaderState,
  | "setFontSize" | "bumpFontSize" | "setLineHeight" | "setFontFamily"
  | "setTheme" | "cycleTheme" | "setColumn" | "saveBookmark" | "clearBookmark"
  | "getBookmark" | "reset" | "hydrate" | "_hydrated"> {
  // Legacy migration shim — prefer namespaced key, fall back to one-shot legacy key.
  const legacyFont = safeRead(LEGACY_FONT_KEY);
  return {
    fontSize: clampNumber(safeRead(KEY_FONT_SIZE) ?? legacyFont, FONT_SIZE_MIN, FONT_SIZE_MAX, DEFAULTS.fontSize),
    lineHeight: clampNumber(safeRead(KEY_LINE_HEIGHT), LINE_HEIGHT_MIN, LINE_HEIGHT_MAX, DEFAULTS.lineHeight),
    fontFamily: pickEnum(safeRead(KEY_FONT_FAMILY), FONT_FAMILIES, DEFAULTS.fontFamily),
    theme: migrateTheme(safeRead(KEY_THEME)) ?? DEFAULTS.theme,
    column: pickEnum(safeRead(KEY_COLUMN), COLUMNS, DEFAULTS.column),
    bookmarks: loadBookmarks(),
  };
}

// SSR-safe initial — same defaults on server and first client paint.
// Real persisted values get patched in via hydrate() on mount.
export const useReaderStore = create<ReaderState>((set, get) => ({
  fontSize: DEFAULTS.fontSize,
  lineHeight: DEFAULTS.lineHeight,
  fontFamily: DEFAULTS.fontFamily,
  theme: DEFAULTS.theme,
  column: DEFAULTS.column,
  bookmarks: {},
  _hydrated: false,

  hydrate() {
    if (get()._hydrated) return;
    if (typeof window === "undefined") return;
    set({ ...readInitial(), _hydrated: true });
  },

  setFontSize(v) {
    const fontSize = clampNumber(v, FONT_SIZE_MIN, FONT_SIZE_MAX, DEFAULTS.fontSize);
    set({ fontSize });
    safeWrite(KEY_FONT_SIZE, String(fontSize));
  },
  bumpFontSize(delta) {
    get().setFontSize(get().fontSize + delta);
  },
  setLineHeight(v) {
    const rounded = Math.round(v * 10) / 10;
    const lineHeight = clampNumber(rounded, LINE_HEIGHT_MIN, LINE_HEIGHT_MAX, DEFAULTS.lineHeight);
    set({ lineHeight });
    safeWrite(KEY_LINE_HEIGHT, String(lineHeight));
  },
  setFontFamily(v) {
    const fontFamily = pickEnum(v, FONT_FAMILIES, DEFAULTS.fontFamily);
    set({ fontFamily });
    safeWrite(KEY_FONT_FAMILY, fontFamily);
  },
  setTheme(v) {
    const theme = migrateTheme(v) ?? DEFAULTS.theme;
    set({ theme });
    safeWrite(KEY_THEME, theme);
  },
  cycleTheme() {
    const cur = get().theme;
    const idx = THEMES.indexOf(cur);
    const next = THEMES[(idx + 1) % THEMES.length] ?? DEFAULTS.theme;
    get().setTheme(next);
  },
  setColumn(v) {
    const column = pickEnum(v, COLUMNS, DEFAULTS.column);
    set({ column });
    safeWrite(KEY_COLUMN, column);
  },
  saveBookmark(storyPath, chapter, position) {
    if (!storyPath) return;
    const safeChapter = Math.max(0, Math.floor(Number(chapter) || 0));
    const entry: ReaderBookmark = { chapter: safeChapter, updatedAt: Date.now() };
    if (typeof position === "number" && Number.isFinite(position)) {
      entry.position = Math.max(0, position);
    }
    const next = { ...get().bookmarks, [storyPath]: entry };
    set({ bookmarks: next });
    safeWrite(KEY_BOOKMARKS, JSON.stringify(next));
  },
  clearBookmark(storyPath) {
    const cur = get().bookmarks;
    if (!(storyPath in cur)) return;
    const next = { ...cur };
    delete next[storyPath];
    set({ bookmarks: next });
    safeWrite(KEY_BOOKMARKS, JSON.stringify(next));
  },
  getBookmark(storyPath) {
    return get().bookmarks[storyPath] ?? null;
  },
  reset() {
    set({
      fontSize: DEFAULTS.fontSize,
      lineHeight: DEFAULTS.lineHeight,
      fontFamily: DEFAULTS.fontFamily,
      theme: DEFAULTS.theme,
      column: DEFAULTS.column,
      bookmarks: {},
    });
    safeRemove(KEY_FONT_SIZE);
    safeRemove(KEY_LINE_HEIGHT);
    safeRemove(KEY_FONT_FAMILY);
    safeRemove(KEY_THEME);
    safeRemove(KEY_COLUMN);
    safeRemove(KEY_BOOKMARKS);
  },
}));
