/**
 * Branching page — interactive story path selection (placeholder logic).
 * Full branching requires API endpoints (Phase 4 scope).
 */

interface BranchingChapter {
  title?: string;
  content?: string;
  [key: string]: unknown;
}

interface BranchingStory {
  chapters?: BranchingChapter[];
  [key: string]: unknown;
}

interface BranchingPipelineResult {
  enhanced?: BranchingStory;
  draft?: BranchingStory;
  [key: string]: unknown;
}

function branchingPage() {
  return {
    message: 'Branching requires a generated story.' as string,

    get hasStory(): boolean {
      return !!Alpine.store('app').pipelineResult;
    },

    get chapters(): BranchingChapter[] {
      const r: BranchingPipelineResult | null = Alpine.store('app').pipelineResult;
      if (!r) return [];
      const story = r.enhanced || r.draft;
      return story?.chapters || [];
    },
  };
}
