/**
 * Reader page — read generated story with chapter navigation.
 */
function readerPage() {
  return {
    chapter: 0,
    fontSize: 18,
    story: null,

    get chapters() {
      if (!this.story) return [];
      return this.story.chapters || [];
    },

    get currentChapter() {
      return this.chapters[this.chapter] || null;
    },

    init() {
      const result = Alpine.store('app').pipelineResult;
      if (result) {
        this.story = result.enhanced || result.draft || null;
      }
    },

    prev() { if (this.chapter > 0) this.chapter--; },
    next() { if (this.chapter < this.chapters.length - 1) this.chapter++; },
  };
}
