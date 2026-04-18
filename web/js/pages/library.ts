/**
 * Library page — browse saved stories and read inline.
 * Combines library (story list) + reader (chapter view) into one page.
 */

interface StoryCheckpoint {
  path: string;
  title?: string;
  genre?: string;
  chapter_count?: number;
  current_layer?: number;
  layer?: number;
  created_at?: string;
  modified?: string;
  size_kb?: number;
  [key: string]: unknown;
}

interface StoryChapter {
  title?: string;
  content?: string;
}

interface StoryContent {
  title?: string;
  genre?: string;
  chapters?: StoryChapter[];
}

interface LoadedStory {
  enhanced?: StoryContent;
  draft?: StoryContent;
  filename?: string;
}

function libraryPage() {
  return {
    // Library state
    stories: [] as StoryCheckpoint[],
    loading: false as boolean,
    error: '' as string,
    loadingStory: null as string | null,
    confirmDelete: null as string | null,
    searchQuery: '' as string,

    // Reader state
    selectedStory: null as LoadedStory | null,
    chapter: 0 as number,
    fontSize: 18 as number,

    // Computed: current view mode
    get isReading(): boolean {
      return this.selectedStory !== null;
    },

    get story(): StoryContent | null {
      if (!this.selectedStory) return null;
      return this.selectedStory.enhanced || this.selectedStory.draft || null;
    },

    get chapters(): StoryChapter[] {
      if (!this.story) return [];
      return this.story.chapters || [];
    },

    get currentChapter(): StoryChapter | null {
      return this.chapters[this.chapter] || null;
    },

    get filteredStories(): StoryCheckpoint[] {
      if (!this.searchQuery) return this.stories;
      const q = this.searchQuery.toLowerCase();
      return this.stories.filter((s: StoryCheckpoint) =>
        (s.title || s.path).toLowerCase().includes(q) ||
        (s.genre || '').toLowerCase().includes(q)
      );
    },

    init(): void {
      this.loadStories();
    },

    async loadStories(): Promise<void> {
      this.loading = true;
      this.error = '';
      try {
        const data = await API.get<{ checkpoints?: StoryCheckpoint[] }>('/pipeline/checkpoints');
        this.stories = data.checkpoints || [];
      } catch (e) {
        this.error = 'Failed to load stories: ' + (e as Error).message;
        this.stories = [];
      }
      this.loading = false;
    },

    async openStory(filename: string): Promise<void> {
      this.loadingStory = filename;
      this.error = '';
      try {
        const data = await API.get<LoadedStory & { error?: string }>('/pipeline/checkpoints/' + encodeURIComponent(filename));
        if (data.error) {
          this.error = data.error;
          this.loadingStory = null;
          return;
        }
        // Set selected story for inline reading
        this.selectedStory = data;
        this.chapter = 0;
        // Also update global stores for compatibility
        Alpine.store('pipeline').result = data;
        Alpine.store('pipeline').status = 'done';
        Alpine.store('pipeline').progress = 4;
        Alpine.store('app').pipelineResult = data;
      } catch (e) {
        this.error = 'Failed to load story: ' + (e as Error).message;
      }
      this.loadingStory = null;
    },

    backToList(): void {
      this.selectedStory = null;
      this.chapter = 0;
    },

    async deleteStory(filename: string): Promise<void> {
      this.error = '';
      try {
        const data = await API.del<{ error?: string }>('/pipeline/checkpoints/' + encodeURIComponent(filename));
        if (data.error) {
          this.error = data.error;
        } else {
          this.stories = this.stories.filter((s: StoryCheckpoint) => s.path !== filename);
        }
      } catch (e) {
        this.error = 'Failed to delete: ' + (e as Error).message;
      }
      this.confirmDelete = null;
    },

    continueStory(story?: StoryCheckpoint): void {
      const s = story || (this.selectedStory ? {
        path: this.selectedStory.filename || '',
        title: this.story?.title || '',
        chapter_count: this.chapters.length,
        genre: this.story?.genre || '',
      } : null);
      if (!s) return;
      Alpine.store('pipeline').startContinuation({
        checkpoint: s.path,
        title: s.title || s.path,
        chapterCount: s.chapter_count || 0,
        genre: s.genre || '',
      });
      Alpine.store('app').navigate('pipeline');
    },

    layerLabel(layer: number): string {
      const labels: Record<number, string> = { 1: 'Draft', 2: 'Enhanced', 3: 'Complete' };
      return labels[layer] || 'Draft';
    },

    layerColor(layer: number): string {
      if (layer >= 3) return 'bg-green-100 text-green-700';
      if (layer === 2) return 'bg-blue-100 text-blue-700';
      return 'bg-amber-100 text-amber-700';
    },

    // Reader navigation
    prev(): void { if (this.chapter > 0) this.chapter--; },
    next(): void { if (this.chapter < this.chapters.length - 1) this.chapter++; },
  };
}
