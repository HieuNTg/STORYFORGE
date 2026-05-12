/**
 * Reader page — read generated story with chapter navigation.
 *
 * Migrated from reader.js (compiled tsc output) to TypeScript source.
 * Logic is verbatim from the compiled output; types added where obvious.
 */

interface StoryData {
  chapters?: ChapterData[];
  title?: string;
  genre?: string;
  [key: string]: unknown;
}

interface ChapterData {
  title?: string;
  content?: string;
  [key: string]: unknown;
}

interface PipelineResultWithStory {
  enhanced?: StoryData;
  draft?: StoryData;
  filename?: string;
  session_id?: string;
  [key: string]: unknown;
}

function readerPage() {
    return {
        chapter: 0,
        fontSize: 18,
        get story(): StoryData | null {
            const result = Alpine.store('app').pipelineResult as PipelineResultWithStory | null;
            if (!result)
                return null;
            return result.enhanced || result.draft || null;
        },
        get chapters(): ChapterData[] {
            if (!this.story)
                return [];
            return this.story.chapters || [];
        },
        get currentChapter(): ChapterData | null {
            return this.chapters[this.chapter] || null;
        },
        get canContinue(): boolean {
            const result = Alpine.store('app').pipelineResult as PipelineResultWithStory | null;
            return !!(result && result.filename);
        },
        continueStory(): void {
            const result = Alpine.store('app').pipelineResult as PipelineResultWithStory | null;
            if (!result)
                return;
            const story = result.enhanced || result.draft;
            Alpine.store('pipeline').startContinuation({
                checkpoint: result.filename || '',
                title: story?.title || '',
                chapterCount: (story?.chapters || []).length,
                genre: story?.genre || '',
            });
            Alpine.store('app').navigate('pipeline');
        },
        prev(): void { if (this.chapter > 0)
            this.chapter--; },
        next(): void { if (this.chapter < this.chapters.length - 1)
            this.chapter++; },
    };
}
