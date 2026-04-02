/**
 * Feedback widget — star rating + comment for chapters.
 * Usage: <div x-data="feedbackWidget('story-id', 0)">...</div>
 *
 * Depends on: Alpine.js 3.x, API global (api-client.js)
 */

document.addEventListener('alpine:init', () => {
  Alpine.data('feedbackWidget', (storyId, chapterIndex) => ({

    // ── State ──────────────────────────────────────────────────────────
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

    // ── Computed ───────────────────────────────────────────────────────
    get canSubmit() {
      return this.rating > 0 && !this.submitting && !this.submitted;
    },

    get dimensionLabels() {
      return {
        coherence: 'Coherence',
        character: 'Characters',
        drama:     'Drama',
        writing:   'Writing',
      };
    },

    // ── Methods ────────────────────────────────────────────────────────
    setRating(n) {
      this.rating = n;
    },

    setScore(dimension, n) {
      this.scores[dimension] = n;
    },

    /**
     * Star fill state for overall rating display.
     * Returns 'filled' | 'empty' for a given star position n (1-5).
     */
    starState(n) {
      const active = this.hoverRating || this.rating;
      return n <= active ? 'filled' : 'empty';
    },

    /**
     * Star fill state for a dimension row.
     */
    dimStarState(dimension, n) {
      const active = this.hoverScores[dimension] || this.scores[dimension];
      return n <= active ? 'filled' : 'empty';
    },

    async submit() {
      if (!this.canSubmit) return;

      this.submitting = true;
      this.error = '';

      // Build overall from dimension average if dimensions were filled,
      // otherwise use the main star rating directly.
      const dimValues = Object.values(this.scores).filter(v => v > 0);
      const overall = dimValues.length === 4
        ? parseFloat((dimValues.reduce((a, b) => a + b, 0) / 4).toFixed(2))
        : this.rating;

      const payload = {
        story_id:      this.storyId,
        chapter_index: this.chapterIndex,
        scores: {
          coherence: this.scores.coherence || this.rating,
          character: this.scores.character || this.rating,
          drama:     this.scores.drama     || this.rating,
          writing:   this.scores.writing   || this.rating,
        },
        overall,
        ...(this.comment.trim() ? { comment: this.comment.trim() } : {}),
      };

      try {
        await API.post('/feedback/rate', payload);
        this.submitted = true;
      } catch (err) {
        this.error = 'Could not submit feedback. Please try again.';
        console.error('[feedbackWidget] submit error:', err);
      } finally {
        this.submitting = false;
      }
    },

    reset() {
      this.rating       = 0;
      this.hoverRating  = 0;
      this.scores       = { coherence: 0, character: 0, drama: 0, writing: 0 };
      this.hoverScores  = { coherence: 0, character: 0, drama: 0, writing: 0 };
      this.comment      = '';
      this.submitted    = false;
      this.submitting   = false;
      this.showDetails  = false;
      this.error        = '';
    },
  }));
});
