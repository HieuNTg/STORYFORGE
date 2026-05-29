/**
 * Genre-aware defaults + range for "tổng số chương" (story target length).
 *
 * Per CEO decision (Option A, 2026-05-26): every story has a planned ending.
 * Numbers tuned for AI-tool reality (token cost, completion likelihood) — not
 * webnovel author norms which run 10x longer.
 */

export const CHAPTER_MIN = 5;
export const CHAPTER_MAX = 200;

interface GenreSpec {
  default: number;
  min: number;
  max: number;
}

/**
 * Key match is case-insensitive on the displayed genre label. Unknown genres
 * fall through to {@link DEFAULT_GENRE_SPEC}.
 */
const GENRE_SPECS: Record<string, GenreSpec> = {
  "tiên hiệp": { default: 60, min: CHAPTER_MIN, max: 200 },
  "huyền huyễn": { default: 50, min: CHAPTER_MIN, max: 200 },
  "kiếm hiệp": { default: 40, min: CHAPTER_MIN, max: 120 },
  "wuxia": { default: 40, min: CHAPTER_MIN, max: 120 },
  "ngôn tình": { default: 20, min: CHAPTER_MIN, max: 50 },
  "ngôn tình cổ trang": { default: 30, min: CHAPTER_MIN, max: 80 },
  "trinh thám": { default: 15, min: CHAPTER_MIN, max: 30 },
  "đô thị": { default: 20, min: CHAPTER_MIN, max: 60 },
  "hiện đại": { default: 20, min: CHAPTER_MIN, max: 60 },
  "khoa huyễn": { default: 25, min: CHAPTER_MIN, max: 80 },
  "lịch sử": { default: 30, min: CHAPTER_MIN, max: 80 },
  "slice of life": { default: 12, min: CHAPTER_MIN, max: 25 },
};

const DEFAULT_GENRE_SPEC: GenreSpec = { default: 20, min: CHAPTER_MIN, max: 100 };

function lookup(genre: string | undefined): GenreSpec {
  if (!genre) return DEFAULT_GENRE_SPEC;
  return GENRE_SPECS[genre.trim().toLowerCase()] ?? DEFAULT_GENRE_SPEC;
}

export function getChapterDefault(genre: string | undefined): number {
  return lookup(genre).default;
}

export function getChapterRange(genre: string | undefined): { min: number; max: number } {
  const spec = lookup(genre);
  return { min: spec.min, max: spec.max };
}

export function clampChapterCount(value: number, genre: string | undefined): number {
  const { min, max } = getChapterRange(genre);
  if (!Number.isFinite(value)) return getChapterDefault(genre);
  return Math.max(min, Math.min(max, Math.round(value)));
}

/**
 * Keep "chương phiên này" within the story's total target. When the user lowers
 * `total` below the current per-session count, the session count must follow it
 * down (you can't write more chapters this session than the whole story plans).
 * A non-finite `total` (e.g. an in-progress empty input) leaves `session` alone.
 */
export function clampSessionToTotal(session: number, total: number): number {
  if (!Number.isFinite(total) || total < 1) return session;
  if (!Number.isFinite(session)) return session;
  return Math.min(session, total);
}
