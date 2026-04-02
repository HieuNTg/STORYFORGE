/**
 * Feedback widget — star rating + comment for chapters.
 * Usage: <div x-data="feedbackWidget('story-id', 0)">...</div>
 *
 * Depends on: Alpine.js 3.x, API global (api-client.js)
 */

interface DimensionScores {
  coherence: number;
  character: number;
  drama:     number;
  writing:   number;
}

interface FeedbackWidgetData {
  storyId: string;
  chapterIndex: number;
  rating: number;
  hoverRating: number;
  scores: DimensionScores;
  hoverScores: DimensionScores;
  comment: string;
  submitted: boolean;
  submitting: boolean;
  showDetails: boolean;
  error: string;
  readonly canSubmit: boolean;
  readonly dimensionLabels: Record<keyof DimensionScores, string>;
  setRating(n: number): void;
  setScore(dimension: keyof DimensionScores, n: number): void;
  starState(n: number): 'filled' | 'empty';
  dimStarState(dimension: keyof DimensionScores, n: number): 'filled' | 'empty';
  submit(): Promise<void>;
  reset(): void;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('feedbackWidget', (storyId: string, chapterIndex: number) => {
    const data: FeedbackWidgetData = {

      // ── State ────────────────────────────────────────────────────────
      storyId,
      chapterIndex,

      /** Overall star rating 1-5; 0 = not yet set */
      rating: 0,
      /** Preview rating while hovering */
      hoverRating: 0,

      /** Per-dimension scores 1-5; 0 = not yet set */
      scores: { coherence: 0, character: 0, drama: 0, writing: 0 },
      /** Dimension hover previews */
      hoverScores: { coherence: 0, character: 0, drama: 0, writing: 0 },

      comment: '',
      submitted: false,
      submitting: false,
      showDetails: false,
      error: '',

      // ── Computed ─────────────────────────────────────────────────────
      get canSubmit(): boolean {
        return data.rating > 0 && !data.submitting && !data.submitted;
      },

      get dimensionLabels(): Record<keyof DimensionScores, string> {
        return {
          coherence: 'Coherence',
          character: 'Characters',
          drama:     'Drama',
          writing:   'Writing',
        };
      },

      // ── Methods ──────────────────────────────────────────────────────
      setRating(n: number): void {
        data.rating = n;
      },

      setScore(dimension: keyof DimensionScores, n: number): void {
        data.scores[dimension] = n;
      },

      /**
       * Star fill state for overall rating display.
       * Returns 'filled' | 'empty' for a given star position n (1-5).
       */
      starState(n: number): 'filled' | 'empty' {
        const active = data.hoverRating || data.rating;
        return n <= active ? 'filled' : 'empty';
      },

      /**
       * Star fill state for a dimension row.
       */
      dimStarState(dimension: keyof DimensionScores, n: number): 'filled' | 'empty' {
        const active = data.hoverScores[dimension] || data.scores[dimension];
        return n <= active ? 'filled' : 'empty';
      },

      async submit(): Promise<void> {
        if (!data.canSubmit) return;

        data.submitting = true;
        data.error = '';

        // Build overall from dimension average if dimensions were filled,
        // otherwise use the main star rating directly.
        const dimValues = Object.values(data.scores).filter((v: number) => v > 0);
        const overall = dimValues.length === 4
          ? parseFloat((dimValues.reduce((a: number, b: number) => a + b, 0) / 4).toFixed(2))
          : data.rating;

        const payload = {
          story_id:      data.storyId,
          chapter_index: data.chapterIndex,
          scores: {
            coherence: data.scores.coherence || data.rating,
            character: data.scores.character || data.rating,
            drama:     data.scores.drama     || data.rating,
            writing:   data.scores.writing   || data.rating,
          },
          overall,
          ...(data.comment.trim() ? { comment: data.comment.trim() } : {}),
        };

        try {
          await API.post('/feedback/rate', payload);
          data.submitted = true;
        } catch (err) {
          data.error = 'Could not submit feedback. Please try again.';
          console.error('[feedbackWidget] submit error:', err);
        } finally {
          data.submitting = false;
        }
      },

      reset(): void {
        data.rating       = 0;
        data.hoverRating  = 0;
        data.scores       = { coherence: 0, character: 0, drama: 0, writing: 0 };
        data.hoverScores  = { coherence: 0, character: 0, drama: 0, writing: 0 };
        data.comment      = '';
        data.submitted    = false;
        data.submitting   = false;
        data.showDetails  = false;
        data.error        = '';
      },
    };
    return data as unknown as Record<string, unknown>;
  });
});
