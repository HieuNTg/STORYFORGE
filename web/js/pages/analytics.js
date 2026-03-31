/**
 * Analytics page — story metrics and quality overview.
 */
function analyticsPage() {
  return {
    loaded: false,
    stats: null,
    _lastResultRef: null,

    get result() {
      return Alpine.store('app').pipelineResult;
    },

    init() {
      // Recompute when pipelineResult changes
      this.$watch('result', (val) => {
        if (val) {
          this.compute();
        } else {
          this.stats = null;
          this.loaded = false;
        }
      });
      // Reset when new pipeline run starts
      this.$watch(() => Alpine.store('pipeline').status, (status) => {
        if (status === 'running') {
          this.stats = null;
          this.loaded = false;
          this._lastResultRef = null;
        }
      });
      // Initial compute if result already exists
      if (this.result) this.compute();
    },

    compute() {
      if (!this.result) return;
      const story = this.result.enhanced || this.result.draft;
      if (!story || !story.chapters) return;

      const chapters = story.chapters;
      // Dedup guard — skip if same result object already computed
      if (this.loaded && this._lastResultRef === this.result) return;

      const totalWords = chapters.reduce((sum, ch) => sum + (ch.content || '').split(/\s+/).length, 0);
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
