/**
 * Reader page — read generated story with chapter navigation.
 */

interface StoryChapter {
  title?: string;
  content?: string;
}

interface StoryContent {
  title?: string;
  genre?: string;
  chapters?: StoryChapter[];
}

interface ReaderPipelineResult {
  enhanced?: StoryContent;
  draft?: StoryContent;
  filename?: string;
}

function readerPage() {
  return {
    chapter: 0 as number,
    fontSize: 18 as number,

    get story(): StoryContent | null {
      const result: ReaderPipelineResult | null = Alpine.store('app').pipelineResult;
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

    get canContinue(): boolean {
      const result: ReaderPipelineResult | null = Alpine.store('app').pipelineResult;
      return !!(result && result.filename);
    },

    continueStory(): void {
      const result: ReaderPipelineResult | null = Alpine.store('app').pipelineResult;
      if (!result) return;
      const story = result.enhanced || result.draft;
      Alpine.store('pipeline').startContinuation({
        checkpoint: result.filename || '',
        title: story?.title || '',
        chapterCount: (story?.chapters || []).length,
        genre: story?.genre || '',
      });
      Alpine.store('app').navigate('pipeline');
    },

    prev(): void { if (this.chapter > 0) this.chapter--; },
    next(): void { if (this.chapter < this.chapters.length - 1) this.chapter++; },
  };
}
