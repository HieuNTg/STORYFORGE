/**
 * Branching page — interactive story path selection (placeholder logic).
 * Full branching requires API endpoints (Phase 4 scope).
 */
function branchingPage() {
  return {
    message: 'Branching requires a generated story.',

    get hasStory() {
      return !!Alpine.store('app').pipelineResult;
    },

    get chapters() {
      const r = Alpine.store('app').pipelineResult;
      if (!r) return [];
      const story = r.enhanced || r.draft;
      return story?.chapters || [];
    },
  };
}
