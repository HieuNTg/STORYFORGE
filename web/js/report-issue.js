/**
 * Report issue button for chapters.
 * Opens a small inline form to report problems with generated content.
 *
 * Usage: <div x-data="reportIssue('story-id', 0)">...</div>
 *
 * Depends on: Alpine.js 3.x, API global (api-client.js)
 */

document.addEventListener('alpine:init', () => {
  Alpine.data('reportIssue', (storyId, chapterIndex) => ({

    // ── State ──────────────────────────────────────────────────────────
    storyId,
    chapterIndex,

    showForm:    false,
    issueType:   '',
    description: '',
    submitting:  false,
    submitted:   false,
    error:       '',

    // ── Computed ───────────────────────────────────────────────────────
    get issueOptions() {
      return [
        { value: 'incoherent',  label: 'Story is incoherent' },
        { value: 'offensive',   label: 'Offensive content'   },
        { value: 'repetitive',  label: 'Repetitive text'     },
        { value: 'other',       label: 'Other issue'         },
      ];
    },

    get canSubmit() {
      return this.issueType !== '' && !this.submitting && !this.submitted;
    },

    // ── Methods ────────────────────────────────────────────────────────
    toggle() {
      this.showForm = !this.showForm;
      if (!this.showForm) this.reset();
    },

    async submitIssue() {
      if (!this.canSubmit) return;

      this.submitting = true;
      this.error = '';

      // Represent the report as a low-score feedback entry so the
      // existing /api/feedback/rate endpoint stores it without a
      // dedicated issues endpoint.
      const payload = {
        story_id:      this.storyId,
        chapter_index: this.chapterIndex,
        scores: { coherence: 1, character: 1, drama: 1, writing: 1 },
        overall: 1.0,
        comment: `[ISSUE:${this.issueType}] ${this.description}`.trim(),
      };

      try {
        await API.post('/feedback/rate', payload);
        this.submitted = true;
        // Auto-close form after 2 s
        setTimeout(() => { this.showForm = false; this.reset(); }, 2000);
      } catch (err) {
        this.error = 'Could not submit report. Please try again.';
        console.error('[reportIssue] submit error:', err);
      } finally {
        this.submitting = false;
      }
    },

    reset() {
      this.issueType   = '';
      this.description = '';
      this.submitted   = false;
      this.submitting  = false;
      this.error       = '';
    },
  }));
});
