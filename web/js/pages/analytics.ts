/**
 * Analytics page — story metrics and quality overview.
 * Supports both current pipeline result and saved stories from Library.
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

interface SavedStoryItem {
  filename: string;
  title: string;
  genre: string;
  chapter_count: number;
  current_layer: number;
  size_kb: number;
  modified: string;
}

interface StoriesResponse {
  items: SavedStoryItem[];
  total: number;
}

function analyticsPage() {
  return {
    loaded: false as boolean,
    stats: null as AnalyticsStats | null,
    _lastResultRef: null as AnalyticsPipelineResult | null,
    stories: [] as SavedStoryItem[],
    loadingStories: false,
    loadingCheckpoint: false,
    selectedStory: null as string | null,
    loadedResult: null as AnalyticsPipelineResult | null,
    storySource: 'current' as 'current' | 'saved',
    $watch: (null as unknown) as AlpineComponent['$watch'],

    get result(): AnalyticsPipelineResult | null {
      if (this.storySource === 'saved' && this.loadedResult) return this.loadedResult;
      return Alpine.store('app').pipelineResult;
    },

    get hasCurrentResult(): boolean {
      return !!Alpine.store('app').pipelineResult;
    },

    get currentStoryTitle(): string {
      const r = this.result;
      if (!r) return '';
      const story = (r.enhanced || r.draft) as { title?: string } | undefined;
      return story?.title || 'Untitled Story';
    },

    init(): void {
      this.fetchStories();
      this.$watch('result', (val: unknown) => {
        if (val) {
          this.compute();
        } else {
          this.stats = null;
          this.loaded = false;
        }
      });
      this.$watch(() => Alpine.store('pipeline').status, (val: unknown) => {
        const status = val as string;
        if (status === 'running') {
          this.stats = null;
          this.loaded = false;
          this._lastResultRef = null;
        }
      });
      if (this.result) this.compute();
    },

    async fetchStories(): Promise<void> {
      this.loadingStories = true;
      try {
        const res: StoriesResponse = await API.get('/pipeline/stories?limit=50');
        this.stories = res.items || [];
      } catch {
        this.stories = [];
      } finally {
        this.loadingStories = false;
      }
    },

    async loadStory(filename: string): Promise<void> {
      this.loadingCheckpoint = true;
      this.selectedStory = filename;
      try {
        const data: AnalyticsPipelineResult = await API.get(`/pipeline/checkpoints/${encodeURIComponent(filename)}`);
        this.loadedResult = data;
        this.storySource = 'saved';
        this._lastResultRef = null;
        this.compute();
      } catch (e) {
        console.error('Failed to load story:', e);
      } finally {
        this.loadingCheckpoint = false;
      }
    },

    useCurrent(): void {
      this.storySource = 'current';
      this.loadedResult = null;
      this.selectedStory = null;
      this._lastResultRef = null;
      this.compute();
    },

    compute(): void {
      if (!this.result) {
        this.stats = null;
        this.loaded = false;
        return;
      }
      const story = this.result.enhanced || this.result.draft;
      if (!story || !story.chapters) {
        this.stats = null;
        this.loaded = false;
        return;
      }

      const chapters = story.chapters;
      if (this.loaded && this._lastResultRef === this.result) return;

      const totalWords = chapters.reduce((sum: number, ch: AnalyticsChapter) => sum + (ch.content || '').split(/\s+/).length, 0);
      const avgWords = chapters.length > 0 ? Math.round(totalWords / chapters.length) : 0;
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
