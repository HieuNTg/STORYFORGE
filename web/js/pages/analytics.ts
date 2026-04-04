/**
 * Analytics page — story metrics and quality overview.
 */

interface AnalyticsStats {
  totalChapters: number;
  totalWords: number;
  avgWords: number;
  readingTime: number;
  quality: unknown | null;
  hasSimulation: boolean;
  eventsCount: number;
}

interface AnalyticsChapter {
  content?: string;
}

interface AnalyticsStory {
  chapters?: AnalyticsChapter[];
}

interface AnalyticsPipelineResult {
  enhanced?: AnalyticsStory;
  draft?: AnalyticsStory;
  quality?: unknown;
  simulation?: { events_count?: number };
}

function analyticsPage() {
  return {
    loaded: false as boolean,
    stats: null as AnalyticsStats | null,
    _lastResultRef: null as AnalyticsPipelineResult | null,
    // Alpine magic — injected at runtime; stub satisfies TypeScript without unsafe double-cast
    $watch: null! as (
      expr: string | (() => unknown),
      cb: (val: unknown) => void
    ) => void,

    get result(): AnalyticsPipelineResult | null {
      return Alpine.store('app').pipelineResult;
    },

    init(): void {
      // Recompute when pipelineResult changes
      this.$watch('result', (val: AnalyticsPipelineResult | null) => {
        if (val) {
          this.compute();
        } else {
          this.stats = null;
          this.loaded = false;
        }
      });
      // Reset when new pipeline run starts
      this.$watch(() => Alpine.store('pipeline').status, (status: string) => {
        if (status === 'running') {
          this.stats = null;
          this.loaded = false;
          this._lastResultRef = null;
        }
      });
      // Initial compute if result already exists
      if (this.result) this.compute();
    },

    compute(): void {
      if (!this.result) return;
      const story = this.result.enhanced || this.result.draft;
      if (!story || !story.chapters) return;

      const chapters = story.chapters;
      // Dedup guard — skip if same result object already computed
      if (this.loaded && this._lastResultRef === this.result) return;

      const totalWords = chapters.reduce((sum: number, ch: AnalyticsChapter) => sum + (ch.content || '').split(/\s+/).length, 0);
      const avgWords = Math.round(totalWords / chapters.length);
      const readingTime = Math.ceil(totalWords / 200);

      this.stats = {
        totalChapters: chapters.length,
        totalWords,
        avgWords,
        readingTime,
        quality: this.result.quality || null,
        hasSimulation: !!this.result.simulation,
        eventsCount: this.result.simulation?.events_count || 0,
      };
      this._lastResultRef = this.result;
      this.loaded = true;
    },
  };
}
