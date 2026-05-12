/**
 * StoryCard — Alpine.data factory for the library card surface.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.4
 *
 * Public API via attrs (declared by the template):
 *   data-story-id        — unique id, propagated on dispatch
 *   data-status          — idle | generating | done | error
 *   data-cover-src       — optional cover image url
 *
 * The factory itself takes props directly; the template binds them and the
 * library page wires `data-status` from the live SSE stream.
 *
 * Composes GenreOrb for the genre badge (the orb is mounted by the template
 * as a sibling x-data instance).
 *
 * Reduced-motion handled by CSS — no scale/lift transforms when the user
 * prefers reduced motion (see components.css).
 */

export type StoryCardStatus = 'idle' | 'generating' | 'done' | 'error';
export type StoryCardMode = 'grid' | 'list';

export interface StoryCardProps {
  storyId: string;
  title: string;
  genreId: string;
  /** Hue passed to the embedded GenreOrb. Optional; orb falls back to its own default. */
  hue?: string;
  /** Cover image url. Empty/undefined → fallback gradient block (template responsibility). */
  coverSrc?: string;
  /** Total chapter count (completed + planned). */
  chapters?: number;
  /** Chapters already generated. Used to compute progress when status==='generating'. */
  chaptersDone?: number;
  status?: StoryCardStatus;
  mode?: StoryCardMode;
}

export interface StoryCardComponent {
  storyId: string;
  title: string;
  genreId: string;
  hue: string;
  coverSrc: string;
  chapters: number;
  chaptersDone: number;
  status: StoryCardStatus;
  mode: StoryCardMode;
  hovered: boolean;
  /** 0..1 progress fraction. Returns 0 when chapters is 0 to avoid div-by-zero. */
  readonly progress: number;
  /** Integer percentage suitable for aria-valuenow / width binding. */
  readonly progressPct: number;
  readonly ariaLabel: string;
  /** True when the progress bar should render (generating + has chapters). */
  readonly showProgress: boolean;
  setStatus(next: StoryCardStatus): void;
  setHovered(next: boolean): void;
  /** Click on the card body. Dispatches sf:story-open. */
  handleOpen(event?: Event): void;
  /** Continue-writing button. */
  handleContinue(event?: Event): void;
  /** Branch button. */
  handleBranch(event?: Event): void;
  /** Delete button. Parent must gate confirmation. */
  handleDelete(event?: Event): void;
}

const STATUS_LABEL: Readonly<Record<StoryCardStatus, string>> = Object.freeze({
  idle: 'ready',
  generating: 'generating',
  done: 'complete',
  error: 'error',
});

export function storyCard(props: StoryCardProps): StoryCardComponent {
  const chapters = sanitizeInt(props.chapters, 0);
  const chaptersDone = clamp(sanitizeInt(props.chaptersDone, 0), 0, chapters);
  return {
    storyId: props.storyId,
    title: props.title,
    genreId: props.genreId,
    hue: props.hue ?? '',
    coverSrc: props.coverSrc ?? '',
    chapters,
    chaptersDone,
    status: props.status ?? 'idle',
    mode: props.mode ?? 'grid',
    hovered: false,

    get progress(): number {
      if (this.chapters <= 0) return 0;
      return clamp(this.chaptersDone / this.chapters, 0, 1);
    },

    get progressPct(): number {
      return Math.round(this.progress * 100);
    },

    get ariaLabel(): string {
      // e.g. "Đại Đạo Triều Thiên, tien-hiep, 12 chapters, complete"
      const parts: string[] = [this.title, this.genreId];
      if (this.chapters > 0) {
        parts.push(`${this.chapters} chapter${this.chapters === 1 ? '' : 's'}`);
      }
      parts.push(STATUS_LABEL[this.status] ?? this.status);
      return parts.join(', ');
    },

    get showProgress(): boolean {
      return this.status === 'generating' && this.chapters > 0;
    },

    setStatus(next: StoryCardStatus): void {
      this.status = next;
    },

    setHovered(next: boolean): void {
      this.hovered = next;
    },

    handleOpen(event?: Event): void {
      // Suppress when nested control was clicked — the buttons stop propagation
      // themselves, so this just guards against unexpected synthetic events.
      dispatch(this as unknown, 'sf:story-open', { id: this.storyId }, event);
    },

    handleContinue(event?: Event): void {
      event?.stopPropagation();
      dispatch(this as unknown, 'sf:story-continue', { id: this.storyId }, event);
    },

    handleBranch(event?: Event): void {
      event?.stopPropagation();
      dispatch(this as unknown, 'sf:story-branch', { id: this.storyId }, event);
    },

    handleDelete(event?: Event): void {
      event?.stopPropagation();
      dispatch(this as unknown, 'sf:story-delete', { id: this.storyId }, event);
    },
  };
}

function clamp(n: number, min: number, max: number): number {
  if (!Number.isFinite(n)) return min;
  if (n < min) return min;
  if (n > max) return max;
  return n;
}

/** Coerce arbitrary input to a non-negative integer; NaN/Infinity → fallback. */
function sanitizeInt(value: number | undefined, fallback: number): number {
  if (value === undefined || !Number.isFinite(value)) return fallback;
  const floored = Math.floor(value as number);
  return floored < 0 ? 0 : floored;
}

function dispatch(
  ctx: unknown,
  name: string,
  detail: Record<string, unknown>,
  _event?: Event,
): void {
  const c = ctx as { $dispatch?: (n: string, d?: unknown) => void };
  if (typeof c.$dispatch === 'function') {
    c.$dispatch(name, detail);
  }
}
