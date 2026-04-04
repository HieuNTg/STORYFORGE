/**
 * Codex page — World Codex / Story Bible viewer.
 *
 * Displays characters, world settings, plot threads, and chapter timeline
 * for a loaded story. Read-only viewer; no editing.
 */

interface CodexCharacter {
  name: string;
  role: string;
  personality: string;
  background: string;
  motivation: string;
  appearance: string;
  relationships: string[];
  reference_image?: string;
}

interface CodexWorld {
  name: string;
  description: string;
  rules: string[];
  locations: string[];
  era: string;
}

interface CodexPlotThread {
  thread_id: string;
  description: string;
  status: string;
  started_chapter: number;
  resolved_chapter: number;
  characters_involved: string[];
}

interface CodexStoryBible {
  premise: string;
  world_rules: string[];
  active_threads: CodexPlotThread[];
  resolved_threads: CodexPlotThread[];
  arc_summaries: string[];
  milestone_events: string[];
}

interface CodexTimelineEntry {
  chapter_number: number;
  title: string;
  summary: string;
  key_events?: string[];
}

interface CodexData {
  title: string;
  genre: string;
  synopsis: string;
  characters: CodexCharacter[];
  world: CodexWorld | null;
  story_bible: CodexStoryBible | null;
  timeline: CodexTimelineEntry[];
  total_chapters: number;
}

function codexPage() {
  return {
    tab: 'characters' as string,
    loading: false as boolean,
    error: '' as string,
    storyId: '' as string,
    data: null as CodexData | null,
    expandedChar: null as number | null,

    get hasStory(): boolean {
      return Alpine.store('app').pipelineResult !== null;
    },

    get currentStoryId(): string {
      const result = Alpine.store('app').pipelineResult as Record<string, unknown> | null;
      return (result?.filename as string) || '';
    },

    init(): void {
      // If a story is already loaded in the pipeline store, auto-load its codex
      if (this.hasStory) {
        const sid = this.currentStoryId;
        if (sid) {
          this.storyId = sid;
          this.load();
        }
      }
    },

    async load(): Promise<void> {
      const id = this.storyId.trim();
      if (!id) {
        this.error = 'Enter a story filename to load.';
        return;
      }
      this.loading = true;
      this.error = '';
      this.data = null;
      try {
        this.data = await API.get<CodexData>('/codex/' + encodeURIComponent(id));
      } catch (e) {
        this.error = 'Failed to load codex: ' + (e as Error).message;
      }
      this.loading = false;
    },

    async loadFromStore(): Promise<void> {
      const sid = this.currentStoryId;
      if (!sid) {
        this.error = 'No story loaded. Open a story from the Library first.';
        return;
      }
      this.storyId = sid;
      await this.load();
    },

    toggleChar(idx: number): void {
      this.expandedChar = this.expandedChar === idx ? null : idx;
    },

    threadStatusClass(status: string): string {
      if (status === 'resolved') return 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300';
      if (status === 'abandoned') return 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400';
      return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300';
    },

    roleClass(role: string): string {
      const r = (role || '').toLowerCase();
      if (r.includes('chính') || r.includes('main') || r.includes('protagonist')) {
        return 'bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300';
      }
      if (r.includes('phản') || r.includes('villain') || r.includes('antagonist')) {
        return 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300';
      }
      return 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300';
    },
  };
}
