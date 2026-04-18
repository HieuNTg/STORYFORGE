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

interface Bookmark {
  id: string;
  node_id: string;
  label: string;
  created_at: string;
}

interface BranchAnalytics {
  total_nodes: number;
  total_choices: number;
  max_depth: number;
  popular_paths: Array<{ path: string[]; count: number }>;
}

interface MergePreview {
  node_a: { id: string; content: string };
  node_b: { id: string; content: string };
  conflicts: string[];
  common_ancestor: string | null;
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

    // Advanced features
    bookmarks: [] as Bookmark[],
    analytics: null as BranchAnalytics | null,
    showBookmarksPanel: false,
    showAnalyticsPanel: false,
    showMergeDialog: false,
    mergeNodeA: '',
    mergeNodeB: '',
    mergeStrategy: 'auto' as 'auto' | 'prefer_a' | 'prefer_b',
    mergePreview: null as MergePreview | null,
    mergeLoading: false,
    mergeError: '',

    // Auto-explore
    showAutoExplore: false,
    autoExploreNumPaths: 3,
    autoExploreDepth: 2,
    autoExplorePaths: [] as Array<{ id: string; nodes: Array<{ content: string; choices: string[] }> }>,
    autoExploreLoading: false,

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
        const res: StoriesResponse = await API.get('/pipeline/stories?limit=50');
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
        const data: BranchingPipelineResult = await API.get(`/pipeline/checkpoints/${encodeURIComponent(filename)}`);
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

    /** Extract story context from active result for branch session. */
    getStoryContext(): Record<string, unknown> {
      const r = this.activeResult;
      if (!r) return {};
      const story = r.enhanced || r.draft;
      if (!story) return {};
      const chars = ((story as Record<string, unknown>).characters as Array<Record<string, string>> || [])
        .slice(0, 10)
        .map(c => ({ name: c.name || '', role: c.role || '', personality: c.personality || '' }));
      const world = (story as Record<string, unknown>).world as Record<string, string> | null;
      const worldSummary = world ? `${world.name || ''}: ${world.description || ''}`.slice(0, 500) : '';
      const conflictWeb = ((story as Record<string, unknown>).conflict_web as Array<Record<string, string>> || []);
      const conflictSummary = conflictWeb
        .filter(c => c.status === 'active')
        .slice(0, 5)
        .map(c => c.description || '')
        .join('; ')
        .slice(0, 500);
      return {
        genre: story.genre || '',
        characters: chars,
        world_summary: worldSummary,
        conflict_summary: conflictSummary,
      };
    },

    // ── Bookmarks ──────────────────────────────────────────────────────────

    async loadBookmarks(sessionId: string): Promise<void> {
      try {
        const res = await API.get<{ bookmarks: Bookmark[] }>(`/branch/${sessionId}/bookmarks`);
        this.bookmarks = res.bookmarks || [];
      } catch {
        this.bookmarks = [];
      }
    },

    async addBookmark(sessionId: string, nodeId: string, label: string): Promise<void> {
      try {
        await API.post(`/branch/${sessionId}/bookmarks`, { node_id: nodeId, label });
        await this.loadBookmarks(sessionId);
      } catch (e) {
        console.error('Failed to add bookmark:', e);
      }
    },

    async removeBookmark(sessionId: string, bookmarkId: string): Promise<void> {
      try {
        await API.del(`/branch/${sessionId}/bookmarks/${bookmarkId}`);
        await this.loadBookmarks(sessionId);
      } catch (e) {
        console.error('Failed to remove bookmark:', e);
      }
    },

    async gotoBookmark(sessionId: string, bookmarkId: string): Promise<void> {
      try {
        await API.post(`/branch/${sessionId}/bookmarks/${bookmarkId}/goto`);
        document.dispatchEvent(new CustomEvent('branch:refresh'));
      } catch (e) {
        console.error('Failed to goto bookmark:', e);
      }
    },

    // ── Analytics ──────────────────────────────────────────────────────────

    async loadAnalytics(sessionId: string): Promise<void> {
      try {
        this.analytics = await API.get<BranchAnalytics>(`/branch/${sessionId}/analytics`);
      } catch {
        this.analytics = null;
      }
    },

    // ── Merge ──────────────────────────────────────────────────────────────

    async loadMergePreview(sessionId: string): Promise<void> {
      if (!this.mergeNodeA || !this.mergeNodeB) {
        this.mergeError = 'Select two nodes to merge';
        return;
      }
      this.mergeLoading = true;
      this.mergeError = '';
      try {
        this.mergePreview = await API.get<MergePreview>(
          `/branch/${sessionId}/merge/preview?node_a=${this.mergeNodeA}&node_b=${this.mergeNodeB}`
        );
      } catch (e) {
        this.mergeError = (e as Error).message || 'Failed to load preview';
        this.mergePreview = null;
      } finally {
        this.mergeLoading = false;
      }
    },

    async executeMerge(sessionId: string): Promise<void> {
      this.mergeLoading = true;
      this.mergeError = '';
      try {
        await API.post(`/branch/${sessionId}/merge`, {
          node_a_id: this.mergeNodeA,
          node_b_id: this.mergeNodeB,
          strategy: this.mergeStrategy,
        });
        this.showMergeDialog = false;
        this.mergePreview = null;
        document.dispatchEvent(new CustomEvent('branch:refresh'));
      } catch (e) {
        this.mergeError = (e as Error).message || 'Merge failed';
      } finally {
        this.mergeLoading = false;
      }
    },

    // ── Auto-explore ───────────────────────────────────────────────────────

    async runAutoExplore(sessionId: string): Promise<void> {
      this.autoExploreLoading = true;
      this.autoExplorePaths = [];
      try {
        const res = await API.post<{ paths: Array<{ id: string; nodes: Array<{ content: string; choices: string[] }> }> }>(
          `/branch/${sessionId}/auto-explore`,
          { num_paths: this.autoExploreNumPaths, depth: this.autoExploreDepth }
        );
        this.autoExplorePaths = res.paths || [];
      } catch (e) {
        console.error('Auto-explore failed:', e);
      } finally {
        this.autoExploreLoading = false;
      }
    },

    // ── Undo/Redo ──────────────────────────────────────────────────────────

    async undo(sessionId: string): Promise<void> {
      try {
        await API.post(`/branch/${sessionId}/undo`);
        document.dispatchEvent(new CustomEvent('branch:refresh'));
      } catch (e) {
        console.error('Undo failed:', e);
      }
    },

    async redo(sessionId: string): Promise<void> {
      try {
        await API.post(`/branch/${sessionId}/redo`);
        document.dispatchEvent(new CustomEvent('branch:refresh'));
      } catch (e) {
        console.error('Redo failed:', e);
      }
    },
  };
}
