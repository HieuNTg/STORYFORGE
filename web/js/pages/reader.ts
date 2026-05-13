/**
 * Reader page — read generated story with chapter navigation.
 *
 * M3 additions (behind STORYFORGE_FORGE_UI flag):
 *   - Chapter navigation sidebar (slide in/out, estimated reading time per chapter)
 *   - Reading progress bar (scroll position 0-100% of current chapter content)
 *   - Inline character portrait fade-in on first mention per chapter
 *   - Font-size toolbar wired to $store.reader (persists via localStorage)
 *
 * When forgeUi flag is OFF the function returns the original shape (backward-compat).
 * Alpine.store calls are wrapped in try/catch with silent no-ops so a missing store
 * never breaks the reader (mirrors M2 bridge pattern).
 */

interface StoryData {
  characters?: CharacterData[];
  chapters?: ChapterData[];
  title?: string;
  genre?: string;
  [key: string]: unknown;
}

interface CharacterData {
  name: string;
  portrait_url?: string | null;
  reference_url?: string | null;
  [key: string]: unknown;
}

interface ChapterData {
  title?: string;
  content?: string;
  number?: number;
  chapter_number?: number;
  [key: string]: unknown;
}

interface PipelineResultWithStory {
  enhanced?: StoryData;
  draft?: StoryData;
  filename?: string;
  session_id?: string;
  [key: string]: unknown;
}

/** Words per minute reading speed estimate for ETA calculation. */
const WPM = 200;

/** Count words in a string (whitespace-split, fast). */
function countWords(text: string): number {
  if (!text) return 0;
  return text.trim().split(/\s+/).filter(Boolean).length;
}

/** Estimated read time in minutes (rounded up, min 1). */
function estimateMinutes(text: string): number {
  const words = countWords(text);
  if (words === 0) return 0;
  return Math.max(1, Math.ceil(words / WPM));
}

/**
 * Parse chapter content into paragraphs and tag the first paragraph that
 * contains a case-insensitive match for `name`.
 * Returns array of { text, portraitUrl | null }.
 */
function parsePortraitParagraphs(
  content: string,
  characters: CharacterData[],
): Array<{ text: string; portraitUrl: string | null }> {
  const paragraphs = content.split(/\n+/).filter((p) => p.trim().length > 0);
  // Track which characters have already had their portrait shown this chapter.
  const shown = new Set<string>();

  return paragraphs.map((text) => {
    let portraitUrl: string | null = null;
    for (const char of characters) {
      if (shown.has(char.name)) continue;
      const url = char.portrait_url || char.reference_url || null;
      if (!url) continue;
      // Case-insensitive substring match.
      if (text.toLowerCase().includes(char.name.toLowerCase())) {
        portraitUrl = url;
        shown.add(char.name);
        break;
      }
    }
    return { text, portraitUrl };
  });
}

/** Silent try/catch wrapper for Alpine.store reads. Returns fallback on error. */
function storeGet<T>(fn: () => T, fallback: T): T {
  try {
    return fn();
  } catch {
    return fallback;
  }
}

function readerPage() {
  return {
    chapter: 0,

    /**
     * Legacy local fontSize — kept for flag-OFF backward compat.
     * When forgeUi is ON, the toolbar drives $store.reader.fontSize instead.
     */
    fontSize: 18,

    /** Sidebar visibility state (M3). */
    sidebarOpen: false,

    /** Scroll progress 0-100 for the progress bar (M3). */
    readingProgress: 0,

    /** Parsed paragraph blocks for the current chapter (M3). */
    paragraphs: [] as Array<{ text: string; portraitUrl: string | null }>,

    /** Whether prefers-reduced-motion is active (M3). */
    reducedMotion: false,

    get story(): StoryData | null {
      const result = storeGet(
        () => Alpine.store('app').pipelineResult as PipelineResultWithStory | null,
        null,
      );
      if (!result) return null;
      return (result.enhanced ?? result.draft) ?? null;
    },

    get chapters(): ChapterData[] {
      if (!this.story) return [];
      return this.story.chapters ?? [];
    },

    get currentChapter(): ChapterData | null {
      return this.chapters[this.chapter] ?? null;
    },

    get canContinue(): boolean {
      const result = storeGet(
        () => Alpine.store('app').pipelineResult as PipelineResultWithStory | null,
        null,
      );
      return !!(result?.filename);
    },

    /** Characters with a portrait/reference URL (M3). */
    get charactersWithPortraits(): CharacterData[] {
      const chars = this.story?.characters ?? [];
      return chars.filter((c) => c.portrait_url ?? c.reference_url);
    },

    /** Whether the Forge UI flag is enabled. */
    get forgeUi(): boolean {
      return storeGet(() => !!Alpine.store('flags')?.forgeUi, false);
    },

    /** Font size from store (if forgeUi) or legacy local field. */
    get activeFontSize(): number {
      if (this.forgeUi) {
        return storeGet(() => (Alpine.store('reader') as { fontSize: number }).fontSize, this.fontSize);
      }
      return this.fontSize;
    },

    /** Estimated read time for a chapter in minutes. */
    readTime(ch: ChapterData): number {
      return estimateMinutes(ch.content ?? '');
    },

    /** Update paragraphs array for current chapter (portrait injection). */
    _rebuildParagraphs(): void {
      const ch = this.currentChapter;
      if (!ch?.content) {
        this.paragraphs = [];
        return;
      }
      if (this.forgeUi) {
        this.paragraphs = parsePortraitParagraphs(
          ch.content,
          this.story?.characters ?? [],
        );
      } else {
        this.paragraphs = [];
      }
    },

    /** Scroll handler: update readingProgress (M3, forgeUi only). */
    _onScroll(): void {
      if (!this.forgeUi) return;
      const el = document.querySelector('[data-reader-content]') as HTMLElement | null;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const total = el.scrollHeight - window.innerHeight;
      if (total <= 0) {
        this.readingProgress = 100;
        return;
      }
      const scrolled = -rect.top;
      this.readingProgress = Math.min(100, Math.max(0, Math.round((scrolled / total) * 100)));
    },

    /** Alpine lifecycle hook. $watch is injected by Alpine at runtime. */
    init(): void {
      // Detect reduced-motion preference.
      try {
        this.reducedMotion =
          typeof window !== 'undefined' &&
          window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches;
      } catch {
        this.reducedMotion = false;
      }

      // Set up scroll listener for progress bar (forgeUi path).
      if (this.forgeUi) {
        const handler = () => { this._onScroll(); };
        window.addEventListener('scroll', handler, { passive: true });
        // Alpine.$watch is available on the component instance at runtime.
        // Cast to any to avoid TS error in non-Alpine context.
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const self = this as any;
        if (typeof self.$watch === 'function') {
          self.$watch('chapter', () => {
            this.readingProgress = 0;
            this._rebuildParagraphs();
            if (!this.reducedMotion) {
              window.scrollTo({ top: 0, behavior: 'smooth' });
            } else {
              window.scrollTo(0, 0);
            }
          });
        }
      }

      this._rebuildParagraphs();
    },

    continueStory(): void {
      const result = storeGet(
        () => Alpine.store('app').pipelineResult as PipelineResultWithStory | null,
        null,
      );
      if (!result) return;
      const story = result.enhanced ?? result.draft;
      try {
        Alpine.store('pipeline').startContinuation({
          checkpoint: result.filename ?? '',
          title: story?.title ?? '',
          chapterCount: (story?.chapters ?? []).length,
          genre: story?.genre ?? '',
        });
        Alpine.store('app').navigate('pipeline');
      } catch {
        /* silent — store may not be initialised in test/legacy context */
      }
    },

    /** Toggle chapter sidebar (M3). */
    toggleSidebar(): void {
      this.sidebarOpen = !this.sidebarOpen;
    },

    prev(): void {
      if (this.chapter > 0) this.chapter--;
    },

    next(): void {
      if (this.chapter < this.chapters.length - 1) this.chapter++;
    },

    goToChapter(idx: number): void {
      if (idx >= 0 && idx < this.chapters.length) {
        this.chapter = idx;
        // Sidebar closes on mobile after navigation.
        if (window.innerWidth < 768) this.sidebarOpen = false;
      }
    },
  };
}

// Expose to Alpine via global registration path.
// The actual Alpine.data() call happens in app.ts; this file just provides
// the factory function at module scope.
if (typeof window !== 'undefined') {
  (window as unknown as Record<string, unknown>).readerPage = readerPage;
}

export { readerPage, estimateMinutes, parsePortraitParagraphs, countWords };
