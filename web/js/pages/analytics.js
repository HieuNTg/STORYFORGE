/**
 * Analytics page — story metrics and quality overview.
 */
function analyticsPage() {
  return {
    loaded: false,
    stats: null,

    get result() {
      return Alpine.store('app').pipelineResult;
    },

    init() {
      if (this.result) this.compute();
    },

    compute() {
      if (!this.result) return;
      const story = this.result.enhanced || this.result.draft;
      if (!story || !story.chapters) return;

      const chapters = story.chapters;
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
      this.loaded = true;
    },
  };
}
