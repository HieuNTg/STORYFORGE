/**
 * Reader page — read generated story with chapter navigation.
 */

interface StoryChapter {
  title?: string;
  content?: string;
}

interface StoryContent {
  chapters?: StoryChapter[];
}

interface PipelineResult {
  enhanced?: StoryContent;
  draft?: StoryContent;
}

function readerPage() {
  return {
    chapter: 0 as number,
    fontSize: 18 as number,

    get story(): StoryContent | null {
      const result: PipelineResult | null = Alpine.store('app').pipelineResult;
      if (!result) return null;
      return result.enhanced || result.draft || null;
    },

    get chapters(): StoryChapter[] {
      if (!this.story) return [];
      return this.story.chapters || [];
    },

    get currentChapter(): StoryChapter | null {
      return this.chapters[this.chapter] || null;
    },

    prev(): void { if (this.chapter > 0) this.chapter--; },
    next(): void { if (this.chapter < this.chapters.length - 1) this.chapter++; },
  };
}
