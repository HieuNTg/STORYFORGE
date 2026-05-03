/**
 * StoryForge — Alpine.js app stores and SPA routing.
 */

// i18n is loaded via separate <script> tag and exposed as window.__sf_i18n
declare const __sf_i18n: any;
const i18n = (window as any).__sf_i18n;

/* ── Domain interfaces ── */

interface NavItem {
  id: string;
  label: string;
  icon: string;
  group: 'main' | 'bottom';
}

type PipelineStatus = 'idle' | 'running' | 'done' | 'error' | 'interrupted';

interface PipelineForm {
  title: string;
  genre: string;
  style: string;
  language: string;
  idea: string;
  num_chapters: number;
  num_characters: number;
  word_count: number;
  num_sim_rounds: number;
  drama_level: string;
  shots_per_chapter: number;
  enable_agents: boolean;
  enable_scoring: boolean;
  enable_media: boolean;
  enable_l1_consistency: boolean;
  // Advanced L1 settings
  enable_emotional_memory: boolean;
  enable_scene_beat_writing: boolean;
  enable_l1_causal_graph: boolean;
  enable_self_review: boolean;
  enable_agent_debate: boolean;
  // Advanced L2 settings
  l2_drama_threshold: number;
  l2_drama_target: number;
  // Quality settings
  enable_quality_gate: boolean;
  quality_gate_threshold: number;
  enable_smart_revision: boolean;
  smart_revision_threshold: number;
}

interface PipelineResult {
  session_id?: string;
  livePreview?: string;
  filename?: string;
  [key: string]: unknown;
}

interface CheckpointItem {
  path: string;
  [key: string]: unknown;
}

interface GenreChoicesResponse {
  genres?: string[];
  styles?: string[];
  drama_levels?: string[];
}

interface ConnectionTestResponse {
  ok: boolean;
  message: string;
}

/* ── Navigation items ── */
const NAV_ITEMS: NavItem[] = [
  { id: 'pipeline',  label: 'Create Story',  icon: 'pencil-square',         group: 'main'   },
  { id: 'library',   label: 'Library',       icon: 'building-library',       group: 'main'   },
  { id: 'export',    label: 'Export',        icon: 'arrow-down-tray',        group: 'main'   },
  { id: 'analytics', label: 'Analytics',     icon: 'chart-bar',              group: 'main'   },
  { id: 'branching', label: 'Branching',     icon: 'arrows-pointing-out',    group: 'main'   },
  { id: 'providers', label: 'Providers',     icon: 'server-stack',           group: 'bottom' },
  { id: 'settings',  label: 'Settings',      icon: 'cog-6-tooth',            group: 'bottom' },
  { id: 'guide',     label: 'Guide',         icon: 'question-mark-circle',   group: 'bottom' },
] as const;

/* ── Global app store ── */
document.addEventListener('alpine:init', () => {

  Alpine.store('i18n', i18n);

  Alpine.store('app', {
    page: 'pipeline' as string,
    sidebarOpen: window.innerWidth > 768,
    /** @deprecated use isLoading instead */
    loading: false,
    /** Global loading overlay flag. Set via setLoading() / clearLoading(). */
    isLoading: false,
    /** Human-readable message shown in the global loading overlay. */
    loadingMessage: '' as string,
    sessionId: null as string | null,
    pipelineResult: null as PipelineResult | null,
    storageWarning: '' as string,
    /** Current theme: 'dark' | 'light'. Reflects the <html> .dark class. */
    darkMode: document.documentElement.classList.contains('dark'),

    navItems: NAV_ITEMS,

    /**
     * Toggle dark mode: flip the .dark class on <html>, persist choice.
     * Uses localStorage directly for the theme pref so it survives sessions
     * (storageManager is session-scoped by default).
     */
    toggleDarkMode(): void {
      this.darkMode = !this.darkMode;
      if (this.darkMode) {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
      // Sync color-scheme so native form controls (inputs, selects) match the theme
      document.documentElement.style.colorScheme = this.darkMode ? 'dark' : 'light';
      try { localStorage.setItem('sf_theme', this.darkMode ? 'dark' : 'light'); } catch (_) {}
    },

    /**
     * Show the global loading overlay.
     * @param msg - Optional message to display.
     */
    setLoading(msg?: string): void {
      this.isLoading = true;
      this.loadingMessage = msg || '';
    },

    /** Hide the global loading overlay. */
    clearLoading(): void {
      this.isLoading = false;
      this.loadingMessage = '';
    },

    /**
     * Navigate to a page and update the URL hash for bookmarkable URLs.
     * Back/forward browser buttons work via the hashchange listener in init().
     * @param page - The page id (must be in NAV_ITEMS).
     */
    navigate(page: string): void {
      this.page = page;
      if (window.innerWidth <= 768) this.sidebarOpen = false;
      // Update hash — #pipeline, #library, etc.
      window.location.hash = page;
    },

    toggleSidebar(): void {
      this.sidebarOpen = !this.sidebarOpen;
    },

    /** Save pipeline result via StorageManager (sessionStorage + IndexedDB fallback) */
    async savePipelineResult(data: PipelineResult): Promise<void> {
      this.pipelineResult = data;
      this.storageWarning = '';
      // Strip transient fields before storage
      const toStore: PipelineResult = { ...data };
      delete toStore.livePreview;
      const json = JSON.stringify(toStore);

      if (json.length > 4 * 1024 * 1024) {
        console.warn('Pipeline result large (' + Math.round(json.length / 1024) + 'KB)');
      }

      await window.storageManager.setItem('sf_result', json);

      if (window.storageManager.isUsingFallback()) {
        console.info('[StorageManager] Saved to IndexedDB fallback.');
      }
    },

    async init(): Promise<void> {
      /**
       * F3: Hash-based URL routing.
       * Supported hashes: #pipeline, #library, #reader, #export,
       *   #settings, #analytics, #branching, #guide
       * Back/forward browser buttons work because hashchange re-syncs the store.
       */
      const resolveHash = (raw: string): string | null => {
        // Strip leading # and optional leading /
        const id = raw.replace(/^#?\/?/, '');
        return NAV_ITEMS.some((n: NavItem) => n.id === id) ? id : null;
      };

      // Restore page from hash on initial load
      const initialPage = resolveHash(window.location.hash);
      if (initialPage) this.page = initialPage;

      // AbortController allows all listeners to be cleaned up via _controller.abort()
      const _controller = new AbortController();
      const _signal = _controller.signal;

      // Sync store when user navigates with back/forward or edits the URL bar
      window.addEventListener('hashchange', (_e: Event): void => {
        const page = resolveHash(window.location.hash);
        if (page && page !== this.page) this.page = page;
      }, { signal: _signal });
      // F6: Auto-manage sidebar on resize (open on desktop, close on mobile)
      window.addEventListener('resize', (_e: Event): void => {
        if (window.innerWidth > 768 && !this.sidebarOpen) {
          this.sidebarOpen = true;
        } else if (window.innerWidth <= 768 && this.sidebarOpen) {
          this.sidebarOpen = false;
        }
      }, { signal: _signal });

      // Issue #6: Notify user once per session when all storage backends fail
      let _storageErrorShown = false;
      window.addEventListener('storage-error', (_e: Event): void => {
        if (_storageErrorShown) return;
        _storageErrorShown = true;
        if (typeof window.sfShowToast === 'function') {
          window.sfShowToast('Storage unavailable — progress may not be saved', 'warning');
        }
      }, { signal: _signal });

      // Restore pipeline result via StorageManager
      await window.storageManager.init();
      try {
        const saved = await window.storageManager.getItem('sf_result');
        if (saved) {
          const parsed: unknown = JSON.parse(saved);
          if (parsed && typeof parsed === 'object') {
            this.pipelineResult = parsed as PipelineResult;
            Alpine.store('pipeline').result = parsed;
            Alpine.store('pipeline').status = 'done';
            Alpine.store('pipeline').progress = 4;
          }
        }
      } catch (e) {
        console.warn('Failed to restore pipeline result:', (e as Error).message);
        await window.storageManager.removeItem('sf_result');
      }
    },
  });

  /* ── Pipeline store ── */
  Alpine.store('pipeline', {
    status: 'idle' as PipelineStatus,
    currentLog: '' as string,
    logs: [] as string[],
    livePreview: '' as string,
    progress: 0,     // 0-4 (layer number)
    result: null as PipelineResult | null,
    error: null as string | null,
    checkpoints: [] as CheckpointItem[],

    // Continuation mode state
    continuationMode: false as boolean,
    // Piece O: optional resume fields surface why the form is pre-filled
    // (only set by resumeStory() from an interrupted-pipeline checkpoint).
    continuationMeta: null as {
      checkpoint: string;
      title: string;
      chapterCount: number;
      genre: string;
      resumeFromChapter?: number;
      targetChapters?: number;
      interruptedAt?: string;
    } | null,

    // Advanced continuation features
    multiPathMode: false as boolean,
    paths: [] as Array<{ id: string; title: string; summary: string; outlines: Array<{ chapter_number: number; title: string; summary: string; key_events: string[] }> }>,
    selectedPathId: null as string | null,

    collaborativeMode: false as boolean,
    collaborativeText: '' as string,
    collaborativeChapterNum: 1 as number,
    collaborativeTitle: '' as string,
    polishLevel: 'light' as 'light' | 'medium' | 'heavy',
    polishedResult: null as { title: string; content: string; word_count: number } | null,

    consistencyMode: false as boolean,
    consistencyReport: null as { issues: Array<{ severity: string; category: string; description: string; suggestion: string; chapter_refs: number[] }>; error_count: number; warning_count: number; is_consistent: boolean } | null,

    outlineMode: false as boolean,
    outlines: [] as Array<{ chapter_number: number; title: string; summary: string; key_events: string[]; scenes: Array<{ beat: string; characters: string[]; location: string }> }>,
    editingOutlineIdx: null as number | null,

    // Form defaults
    form: {
      title: '', genre: 'Tiên Hiệp', style: 'Miêu tả chi tiết', language: 'vi',
      idea: '', num_chapters: 5, num_characters: 5, word_count: 2000,
      num_sim_rounds: 3, drama_level: 'cao', shots_per_chapter: 8,
      enable_agents: true, enable_scoring: true, enable_media: false,
      lite_mode: false, // Skip L2 enhancement
      enable_l1_consistency: false,
      // Advanced L1 settings
      enable_emotional_memory: true,
      enable_proactive_constraints: true,
      enable_thread_enforcement: true,
      enable_emotional_bridge: true,
      enable_scene_beat_writing: true,
      enable_l1_causal_graph: true,
      enable_self_review: true,
      enable_agent_debate: true,
      // Advanced L2 settings
      l2_drama_threshold: 0.5,
      l2_drama_target: 0.65,
      // Quality settings
      enable_quality_gate: true,
      quality_gate_threshold: 2.5,
      enable_smart_revision: true,
      smart_revision_threshold: 3.5,
    } as PipelineForm,

    genres: [] as string[], styles: [] as string[], dramaLevels: [] as string[],
    languages: [
      { code: 'vi', name: 'Tiếng Việt' },
      { code: 'en', name: 'English' },
      { code: 'zh', name: '中文' },
    ] as Array<{ code: string; name: string }>,
    templates: {} as Record<string, unknown>,

    async loadChoices(): Promise<void> {
      try {
        const data = await API.get<GenreChoicesResponse>('/pipeline/genres');
        this.genres = data.genres || [];
        this.styles = data.styles || [];
        this.dramaLevels = data.drama_levels || [];
      } catch (e) { console.error('Load choices failed:', e); }
    },

    async loadTemplates(): Promise<void> {
      try {
        this.templates = await API.get<Record<string, unknown>>('/pipeline/templates');
      } catch (e) { console.error('Load templates failed:', e); }
    },

    async _streamPipeline(url: string, body: Record<string, unknown>): Promise<void> {
      this.status = 'running';
      this.logs = [];
      this.livePreview = '';
      this.progress = 0;
      this.result = null;
      this.error = null;

      try {
        for await (const event of API.stream(url, body)) {
          if (event.type === 'session') {
            Alpine.store('app').sessionId = event.session_id ?? null;
          } else if (event.type === 'log') {
            this.currentLog = event.data as string;
            this.logs.push(event.data as string);
            this.progress = this._detectLayer(event.data as string);
          } else if (event.type === 'stream') {
            this.livePreview = event.data as string;
          } else if (event.type === 'done') {
            const result = event.data as PipelineResult;
            this.result = result;
            Alpine.store('app').savePipelineResult(result);
            Alpine.store('app').sessionId = result.session_id ?? null;
            this.status = 'done';
            this.progress = 4;
          } else if (event.type === 'error') {
            this.error = event.data as string;
            this.status = 'error';
          } else if (event.type === 'interrupted') {
            this.error = 'Connection lost. You can resume from the last checkpoint.';
            this.status = 'interrupted';
          }
        }
        if (this.status === 'running') this.status = 'done';
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    async run(): Promise<void> {
      const idea = (this.form.idea || '').trim();
      if (!idea || idea.length < 10) {
        this.error = 'Please enter a story idea (at least 10 characters).';
        this.status = 'error';
        return;
      }
      await this._streamPipeline('/pipeline/run', this.form as PipelineForm & Record<string, unknown>);
    },

    startContinuation(meta: {
      checkpoint: string;
      title: string;
      chapterCount: number;
      genre: string;
      resumeFromChapter?: number;
      targetChapters?: number;
      interruptedAt?: string;
    }): void {
      this.continuationMode = true;
      this.continuationMeta = meta;
      this.status = 'idle';
      this.result = null;
      this.error = null;
      this.logs = [];
      this.livePreview = '';
      this.progress = 0;
    },

    async runContinuation(): Promise<void> {
      if (!this.continuationMeta) return;
      await this._streamPipeline('/pipeline/continue', {
        checkpoint: this.continuationMeta.checkpoint,
        additional_chapters: this.form.num_chapters,
        word_count: this.form.word_count,
        style: this.form.style,
        run_enhancement: this.form.enable_agents,
        num_sim_rounds: this.form.num_sim_rounds,
      });
    },

    async loadCheckpoints(): Promise<void> {
      try {
        const data = await API.get<{ checkpoints?: CheckpointItem[] }>('/pipeline/checkpoints');
        this.checkpoints = data.checkpoints || [];
      } catch (e) {
        console.error('Load checkpoints failed:', e);
        this.checkpoints = [];
      }
    },

    async resumeFromCheckpoint(path: string): Promise<void> {
      await this._streamPipeline('/pipeline/resume', { checkpoint: path });
    },

    _detectLayer(msg: string): number {
      const up = msg.toUpperCase();
      if (up.includes('MEDIA') || up.includes('IMAGE')) return 3;
      if (up.includes('LAYER 2') || up.includes('MÔ PHỎNG') || up.includes('ENHANCE')) return 2;
      if (up.includes('LAYER 1') || up.includes('TẠO TRUYỆN') || up.includes('CHƯƠNG')) return 1;
      return this.progress || 0;
    },

    // ═══ Multi-Path Preview ═══
    async generatePaths(numPaths: number = 3): Promise<void> {
      if (!this.continuationMeta) return;
      this.status = 'running';
      this.error = null;
      this.paths = [];
      try {
        const data = await API.post<{ paths: Array<{ id: string; title: string; summary: string; outlines: Array<{ chapter_number: number; title: string; summary: string; key_events: string[] }> }> }>('/pipeline/continue/paths', {
          checkpoint: this.continuationMeta.checkpoint,
          additional_chapters: this.form.num_chapters,
          num_paths: numPaths,
        });
        this.paths = data.paths || [];
        this.multiPathMode = true;
        this.status = 'idle';
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    async selectPath(pathId: string): Promise<void> {
      const path = this.paths.find(p => p.id === pathId);
      if (!path || !this.continuationMeta) return;
      this.selectedPathId = pathId;
      await this._streamPipeline('/pipeline/continue/select-path', {
        checkpoint: this.continuationMeta.checkpoint,
        path_id: pathId,
        outlines: path.outlines,
        word_count: this.form.word_count,
        style: this.form.style,
      });
      this.multiPathMode = false;
      this.paths = [];
    },

    // ═══ Outline Preview & Edit ═══
    async generateOutlines(): Promise<void> {
      if (!this.continuationMeta) return;
      this.status = 'running';
      this.error = null;
      try {
        const data = await API.post<{ outlines: Array<{ chapter_number: number; title: string; summary: string; key_events: string[]; scenes: Array<{ beat: string; characters: string[]; location: string }> }> }>('/pipeline/continue/outlines', {
          checkpoint: this.continuationMeta.checkpoint,
          additional_chapters: this.form.num_chapters,
        });
        this.outlines = data.outlines || [];
        this.outlineMode = true;
        this.status = 'idle';
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    async writeFromOutlines(): Promise<void> {
      if (!this.continuationMeta || this.outlines.length === 0) return;
      await this._streamPipeline('/pipeline/continue/write', {
        checkpoint: this.continuationMeta.checkpoint,
        outlines: this.outlines,
        word_count: this.form.word_count,
        style: this.form.style,
      });
      this.outlineMode = false;
      this.outlines = [];
    },

    // ═══ Collaborative Mode ═══
    async polishChapter(): Promise<void> {
      if (!this.continuationMeta || !this.collaborativeText.trim()) return;
      this.status = 'running';
      this.error = null;
      this.polishedResult = null;
      try {
        for await (const event of API.stream('/pipeline/collaborative-chapter', {
          checkpoint: this.continuationMeta.checkpoint,
          chapter_number: this.collaborativeChapterNum,
          user_text: this.collaborativeText,
          title: this.collaborativeTitle,
          polish_level: this.polishLevel,
        })) {
          if (event.type === 'progress') {
            this.currentLog = event.data as string;
            this.logs.push(event.data as string);
          } else if (event.type === 'done') {
            const result = event.data as { title: string; content: string; word_count: number };
            this.polishedResult = result;
            this.status = 'done';
          } else if (event.type === 'error') {
            this.error = event.data as string;
            this.status = 'error';
          }
        }
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    // ═══ Consistency Check ═══
    async checkConsistency(chapterNumbers?: number[]): Promise<void> {
      if (!this.continuationMeta) return;
      this.status = 'running';
      this.error = null;
      this.consistencyReport = null;
      try {
        for await (const event of API.stream('/pipeline/check-consistency', {
          checkpoint: this.continuationMeta.checkpoint,
          chapter_numbers: chapterNumbers || [],
        })) {
          if (event.type === 'progress') {
            this.currentLog = event.data as string;
            this.logs.push(event.data as string);
          } else if (event.type === 'done') {
            this.consistencyReport = event.data as typeof this.consistencyReport;
            this.consistencyMode = true;
            this.status = 'done';
          } else if (event.type === 'error') {
            this.error = event.data as string;
            this.status = 'error';
          }
        }
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    // Piece O: clear the resume callout without resetting the whole pipeline state.
    // Used by the dismiss "X" on the resume banner so the user can start fresh
    // without losing form values they may have already tweaked.
    dismissContinuationCallout(): void {
      this.continuationMode = false;
      this.continuationMeta = null;
    },

    reset(): void {
      this.status = 'idle';
      this.logs = [];
      this.livePreview = '';
      this.progress = 0;
      this.result = null;
      this.error = null;
      this.checkpoints = [];
      this.continuationMode = false;
      this.continuationMeta = null;
      // Reset advanced features
      this.multiPathMode = false;
      this.paths = [];
      this.selectedPathId = null;
      this.collaborativeMode = false;
      this.collaborativeText = '';
      this.polishedResult = null;
      this.consistencyMode = false;
      this.consistencyReport = null;
      this.outlineMode = false;
      this.outlines = [];
      this.editingOutlineIdx = null;
    },
  });

  /* ── Settings store ── */
  Alpine.store('settings', {
    config: null as Record<string, unknown> | null,
    saving: false,
    message: '' as string,

    async load(): Promise<void> {
      try {
        this.config = await API.get<Record<string, unknown>>('/config');
      } catch (e) { console.error('Load config failed:', e); }
    },

    async save(formData: Record<string, unknown>): Promise<void> {
      this.saving = true;
      this.message = '';
      try {
        await API.put('/config', formData);
        this.message = 'Settings saved!';
        await this.load();
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.saving = false;
    },

    async testConnection(): Promise<string> {
      try {
        const res = await API.post<ConnectionTestResponse>('/config/test-connection');
        return res.ok ? 'OK: ' + res.message : 'Error: ' + res.message;
      } catch (e) { return 'Error: ' + (e as Error).message; }
    },
  });

  // Init: load choices and config
  Alpine.store('pipeline').loadChoices();
  Alpine.store('pipeline').loadTemplates();
  Alpine.store('settings').load();
});
