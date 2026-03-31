/**
 * Reader page — read generated story with chapter navigation.
 */
function readerPage() {
  return {
    chapter: 0,
    fontSize: 18,

    get story() {
      const result = Alpine.store('app').pipelineResult;
      if (!result) return null;
      return result.enhanced || result.draft || null;
    },

    get chapters() {
      if (!this.story) return [];
      return this.story.chapters || [];
    },

    get currentChapter() {
      return this.chapters[this.chapter] || null;
    },

    prev() { if (this.chapter > 0) this.chapter--; },
    next() { if (this.chapter < this.chapters.length - 1) this.chapter++; },
  };
}
