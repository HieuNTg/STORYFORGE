/**
 * Pipeline page — main story generation form and result display.
 */

function pipelinePage() {
  return {
    activeTab: 'draft' as string,
    branchOpen: false as boolean,
    _branchComp: null as unknown,

    /** Example story ideas for quick start */
    ideaExamples: [
      { title: 'Tiên Hiệp', genre: 'Tiên Hiệp', idea: 'Một thiếu niên bình thường phát hiện mình sở hữu linh căn hiếm có', teaser: 'Tu tiên giả tưởng với hệ thống cảnh giới' },
      { title: 'Đô Thị', genre: 'Đô Thị', idea: 'CEO trẻ tuổi gặp lại mối tình đầu sau 10 năm xa cách', teaser: 'Tình yêu lãng mạn giữa phố thị hiện đại' },
      { title: 'Huyền Huyễn', genre: 'Huyền Huyễn', idea: 'Một pháp sư yếu đuối tình cờ đánh thức sức mạnh cổ đại', teaser: 'Ma pháp và phiêu lưu trong thế giới fantasy' },
      { title: 'Xuyên Không', genre: 'Xuyên Không', idea: 'Nữ bác sĩ hiện đại xuyên về thời cổ đại làm hoàng phi', teaser: 'Tri thức hiện đại gặp âm mưu cung đình' },
    ] as Array<{ title: string; genre: string; idea: string; teaser: string }>,
    // Alpine magic properties — declared here so TypeScript sees them; Alpine injects real implementations at runtime.
    $watch: (null as unknown) as AlpineComponent['$watch'],
    $nextTick: (null as unknown) as ((() => Promise<void>) & ((cb: () => void) => void)),
    $refs: (null as unknown) as Record<string, HTMLElement & { _x_dataStack?: Array<{ startSession?: (t: string) => void }> }>,

    /**
     * Form persistence helpers — saves genre, idea, style, num_chapters
     * to localStorage under 'sf_form_state' as a JSON blob.
     * Called from _watchFormState() on any of those field changes.
     */
    _saveFormState(): void {
      try {
        const f = Alpine.store('pipeline').form;
        const state = {
          genre:        f.genre,
          idea:         f.idea,
          style:        f.style,
          num_chapters: f.num_chapters,
        };
        localStorage.setItem('sf_form_state', JSON.stringify(state));
      } catch (_) {}
    },

    /**
     * Restore form state from localStorage on page init.
     * Only restores the four persisted fields; leaves other form values
     * at their defaults so server-driven values (genres list, etc.) can
     * fill in without conflict.
     */
    async _restoreFormState(): Promise<void> {
      try {
        const raw = localStorage.getItem('sf_form_state');
        if (!raw) return;
        const state = JSON.parse(raw);
        const f = Alpine.store('pipeline').form;
        if (state.genre)        f.genre        = state.genre;
        if (state.idea)         f.idea         = state.idea;
        if (state.style)        f.style        = state.style;
        if (state.num_chapters) f.num_chapters = state.num_chapters;
      } catch (_) {}
    },

    /** Set up $watch listeners for the four persisted form fields. */
    _watchFormState(): void {
      const save = () => this._saveFormState();
      this.$watch(() => Alpine.store('pipeline').form.genre,        save);
      this.$watch(() => Alpine.store('pipeline').form.idea,         save);
      this.$watch(() => Alpine.store('pipeline').form.style,        save);
      this.$watch(() => Alpine.store('pipeline').form.num_chapters, save);
    },

    async init(): Promise<void> {
      // Restore saved form state, then start watching for changes
      await this._restoreFormState();
      this._watchFormState();
    },

    /**
     * Piece O: Compact "X giờ trước" formatter for the resume callout.
     * Mirrors library.ts to keep the banner self-contained — KISS, no shared util layer.
     */
    relativeTimeVi(iso: string): string {
      const t = Date.parse(iso);
      if (!Number.isFinite(t)) return '';
      const diff = Math.max(0, Date.now() - t);
      const minutes = Math.floor(diff / 60_000);
      if (minutes < 1) return 'vừa xong';
      if (minutes < 60) return `${minutes} phút trước`;
      const hours = Math.floor(minutes / 60);
      if (hours < 24) return `${hours} giờ trước`;
      const days = Math.floor(hours / 24);
      return `${days} ngày trước`;
    },

    /**
     * Piece P: Format elapsed run time for the post-resume success ribbon.
     * Returns "X giây" when under a minute, otherwise "Y phút".
     * KISS: short durations are common (cached/quick runs); longer than an
     * hour is unlikely for resume deltas, so we don't bother with hours.
     */
    formatElapsedVi(startedAt: number | null, finishedAt: number | null): string {
      if (startedAt == null || finishedAt == null || finishedAt < startedAt) return '';
      const diff = finishedAt - startedAt;
      if (diff < 60_000) return `${Math.max(1, Math.floor(diff / 1000))} giây`;
      const minutes = Math.floor(diff / 60_000);
      return `${minutes} phút`;
    },

    /**
     * Piece P: Compute the inclusive chapter range for the success ribbon.
     * Falls back to resumeFromChapter + form delta when targetChapters is
     * missing (legacy checkpoints don't always carry that field).
     */
    resumeRangeEnd(): number {
      const store = Alpine.store('pipeline') as
        { continuationMeta: { resumeFromChapter?: number; targetChapters?: number } | null;
          form: { num_chapters: number } };
      const meta = store.continuationMeta;
      if (!meta) return 0;
      const start = meta.resumeFromChapter || 1;
      if (meta.targetChapters && meta.targetChapters >= start) return meta.targetChapters;
      return start + Math.max(0, (store.form?.num_chapters || 1) - 1);
    },

    /**
     * Piece P: open the reader for the just-finished story and clear the
     * resume ribbon. Mirrors library.openStory() — we set the page first so
     * the library's x-init can pick up the filename and load it.
     *
     * Piece Q: also flag pendingJumpAfterOpen so library.openStory() jumps
     * straight to the first newly-added chapter after the story loads.
     */
    openReaderFromRibbon(): void {
      const pipelineStore = Alpine.store('pipeline') as
        { result: { filename?: string } | null;
          pendingJumpAfterOpen: boolean;
          clearResumeRibbon(): void };
      const filename = pipelineStore.result?.filename;
      // Set BEFORE clearResumeRibbon — clearResumeRibbon nukes continuationMeta
      // but we need this flag to survive into library.openStory.
      pipelineStore.pendingJumpAfterOpen = true;
      pipelineStore.clearResumeRibbon();
      Alpine.store('app').navigate('library');
      if (filename) {
        // Defer so the library page mounts before openStory is called.
        setTimeout(() => {
          const lib = document.querySelector('[x-data*="libraryPage"]') as
            HTMLElement & { _x_dataStack?: Array<{ openStory?: (f: string) => void }> } | null;
          const ctx = lib?._x_dataStack?.[0];
          if (ctx?.openStory) ctx.openStory(filename);
        }, 50);
      }
    },

    get isContinuation(): boolean {
      return Alpine.store('pipeline').continuationMode;
    },

    /** Returns phase state: 'idle' | 'active' | 'done' based on pipeline progress */
    getPhaseState(phaseIndex: number): string {
      const store = Alpine.store('pipeline') as { status: string; progress: number };
      if (store.status === 'idle' || store.status === 'error') return 'idle';
      if (store.status === 'done') return 'done';
      // 6 phases: 0-16.6% = phase 0, 16.7-33.3% = phase 1, etc.
      const phaseProgress = (store.progress / 100) * 6;
      const currentPhase = Math.floor(phaseProgress);
      if (phaseIndex < currentPhase) return 'done';
      if (phaseIndex === currentPhase) return 'active';
      return 'idle';
    },

    /** Estimated time based on chapter count */
    get estimateTime(): string {
      const store = Alpine.store('pipeline') as { form: { num_chapters: number }; continuationMode: boolean };
      const chapters = store.continuationMode ? store.form.num_chapters : store.form.num_chapters;
      const minutes = Math.ceil(chapters * 1.5);
      return minutes < 60 ? `${minutes}m` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
    },

    /** Estimated cost based on chapter count */
    get estimateCost(): string {
      const store = Alpine.store('pipeline') as { form: { num_chapters: number } };
      const cost = store.form.num_chapters * 0.02;
      return `$${cost.toFixed(2)}`;
    },

    async runPipeline(): Promise<void> {
      this.activeTab = 'draft';
      if (this.isContinuation) {
        await Alpine.store('pipeline').runContinuation();
      } else {
        await Alpine.store('pipeline').run();
      }
    },

    async openBranchMode(): Promise<void> {
      const result = Alpine.store('pipeline').result;
      if (!result) return;
      const story = result.enhanced || result.draft;
      if (!story) return;
      // Collect chapter texts
      const chapters = (story.chapters || []) as Array<{ title?: string; content?: string }>;
      const text = chapters.map(ch => (ch.title ? ch.title + '\n' : '') + ch.content).join('\n\n');
      this.branchOpen = true;
      await this.$nextTick();
      const el = this.$refs['branchPanel'];
      if (el && el._x_dataStack) {
        const comp = el._x_dataStack[0];
        if (comp && typeof comp.startSession === 'function') {
          comp.startSession(text);
        }
      }
    },
  };
}
