/**
 * Branching page — story loading, chapter selection, and branch session management.
 * Supports two story sources: current pipeline result (in-memory) and saved checkpoints.
 */

interface BranchingChapter {
  number?: number;
  title?: string;
  content?: string;
  [key: string]: unknown;
}

interface BranchingStory {
  title?: string;
  genre?: string;
  chapters?: BranchingChapter[];
  [key: string]: unknown;
}

interface BranchingPipelineResult {
  enhanced?: BranchingStory;
  draft?: BranchingStory;
  has_enhanced?: boolean;
  has_draft?: boolean;
  [key: string]: unknown;
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

function branchingPage() {
  return {
    selectedChapter: null as number | null,
    stories: [] as SavedStoryItem[],
    loadedStory: null as BranchingPipelineResult | null,
    loadingStories: false,
    loadingCheckpoint: false,
    showStoryPicker: false,
    storySource: 'current' as 'current' | 'saved',
    loadError: '',
    restoringSession: false,
    pendingRestoreSessionId: null as string | null,

    init() {
      this.fetchStories();
      (this as unknown as AlpineComponent).$el.addEventListener('branch-close', () => {
        this.selectedChapter = null;
        clearBranchSession();
      });
      document.addEventListener('branch:started', ((e: CustomEvent) => {
        if (this.selectedChapter !== null) {
          saveBranchSession(e.detail.sessionId, this.selectedChapter, this.storyTitle);
        }
      }) as EventListener);
      this.tryRestoreSession();
    },

    async tryRestoreSession() {
      const saved = loadBranchSession();
      if (!saved) return;
      this.restoringSession = true;
      try {
        const res = await fetch(`/api/branch/${saved.sessionId}/current`);
        if (res.ok) {
          this.pendingRestoreSessionId = saved.sessionId;
          this.selectedChapter = saved.chapterIndex;
        } else {
          clearBranchSession();
        }
      } catch {
        clearBranchSession();
      } finally {
        this.restoringSession = false;
      }
    },

    get hasCurrentStory(): boolean {
      return !!Alpine.store('app').pipelineResult;
    },

    get hasAnyStory(): boolean {
      return this.hasCurrentStory || this.loadedStory !== null;
    },

    get activeResult(): BranchingPipelineResult | null {
      if (this.storySource === 'saved' && this.loadedStory) return this.loadedStory;
      return Alpine.store('app').pipelineResult as BranchingPipelineResult | null;
    },

    get chapters(): BranchingChapter[] {
      const r = this.activeResult;
      if (!r) return [];
      const story = r.enhanced || r.draft;
      return story?.chapters || [];
    },

    get storyTitle(): string {
      const r = this.activeResult;
      if (!r) return '';
      const story = r.enhanced || r.draft;
      return story?.title || 'Untitled';
    },

    getChapterContent(idx: number): string {
      const r = this.activeResult;
      if (!r) return '';
      const enhanced = r.enhanced?.chapters?.[idx];
      const draft = r.draft?.chapters?.[idx];
      return enhanced?.content || draft?.content || '';
    },

    async fetchStories() {
      this.loadingStories = true;
      try {
        const res: StoriesResponse = await API.get('/v1/pipeline/stories?limit=50');
        this.stories = res.items || [];
      } catch {
        this.stories = [];
      } finally {
        this.loadingStories = false;
      }
    },

    async loadStory(filename: string) {
      this.loadingCheckpoint = true;
      this.loadError = '';
      try {
        const data: BranchingPipelineResult = await API.get(`/v1/pipeline/checkpoints/${encodeURIComponent(filename)}`);
        this.loadedStory = data;
        this.storySource = 'saved';
        this.selectedChapter = null;
        this.showStoryPicker = false;
      } catch (e) {
        this.loadError = (e as Error).message || 'Failed to load story';
      } finally {
        this.loadingCheckpoint = false;
      }
    },

    useCurrent() {
      this.storySource = 'current';
      this.loadedStory = null;
      this.selectedChapter = null;
      this.showStoryPicker = false;
    },

    selectChapter(idx: number) {
      if (this.selectedChapter === idx) {
        this.selectedChapter = null;
        clearBranchSession();
        return;
      }
      this.selectedChapter = idx;
    },

    getSelectedContent(): string {
      if (this.selectedChapter === null) return '';
      return this.getChapterContent(this.selectedChapter);
    },
  };
}
