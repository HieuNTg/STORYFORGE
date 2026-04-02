/**
 * Report issue button for chapters.
 * Opens a small inline form to report problems with generated content.
 *
 * Usage: <div x-data="reportIssue('story-id', 0)">...</div>
 *
 * Depends on: Alpine.js 3.x, API global (api-client.js)
 */

interface IssueOption {
  value: string;
  label: string;
}

interface ReportIssueData {
  storyId: string;
  chapterIndex: number;
  showForm: boolean;
  issueType: string;
  description: string;
  submitting: boolean;
  submitted: boolean;
  error: string;
  readonly issueOptions: IssueOption[];
  readonly canSubmit: boolean;
  toggle(): void;
  submitIssue(): Promise<void>;
  reset(): void;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('reportIssue', (storyId: string, chapterIndex: number) => {
    const data: ReportIssueData = {

      // ── State ────────────────────────────────────────────────────────
      storyId,
      chapterIndex,

      showForm:    false,
      issueType:   '',
      description: '',
      submitting:  false,
      submitted:   false,
      error:       '',

      // ── Computed ─────────────────────────────────────────────────────
      get issueOptions(): IssueOption[] {
        return [
          { value: 'incoherent',  label: 'Story is incoherent' },
          { value: 'offensive',   label: 'Offensive content'   },
          { value: 'repetitive',  label: 'Repetitive text'     },
          { value: 'other',       label: 'Other issue'         },
        ];
      },

      get canSubmit(): boolean {
        return data.issueType !== '' && !data.submitting && !data.submitted;
      },

      // ── Methods ──────────────────────────────────────────────────────
      toggle(): void {
        data.showForm = !data.showForm;
        if (!data.showForm) data.reset();
      },

      async submitIssue(): Promise<void> {
        if (!data.canSubmit) return;

        data.submitting = true;
        data.error = '';

        // Represent the report as a low-score feedback entry so the
        // existing /api/feedback/rate endpoint stores it without a
        // dedicated issues endpoint.
        const payload = {
          story_id:      data.storyId,
          chapter_index: data.chapterIndex,
          scores: { coherence: 1, character: 1, drama: 1, writing: 1 },
          overall: 1.0,
          comment: `[ISSUE:${data.issueType}] ${data.description}`.trim(),
        };

        try {
          await API.post('/feedback/rate', payload);
          data.submitted = true;
          // Auto-close form after 2 s
          setTimeout(() => { data.showForm = false; data.reset(); }, 2000);
        } catch (err) {
          data.error = 'Could not submit report. Please try again.';
          console.error('[reportIssue] submit error:', err);
        } finally {
          data.submitting = false;
        }
      },

      reset(): void {
        data.issueType   = '';
        data.description = '';
        data.submitted   = false;
        data.submitting  = false;
        data.error       = '';
      },
    };
    return data as unknown as Record<string, unknown>;
  });
});
