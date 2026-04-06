/**
 * Pipeline page — main story generation form and result display.
 */

function pipelinePage() {
  return {
    activeTab: 'draft' as string,
    branchOpen: false as boolean,
    _branchComp: null as unknown,
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

    async runPipeline(): Promise<void> {
      this.activeTab = 'draft';
      await Alpine.store('pipeline').run();
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
