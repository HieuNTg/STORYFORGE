/**
 * Export page — download story in various formats.
 */
function exportPage() {
  return {
    exporting: null as string | null,
    message: '' as string,
    stories: [] as { filename: string; title: string; genre: string; chapter_count: number; modified: string }[],
    selectedStory: '' as string,
    loading: false,

    get sessionId(): string | null {
      return Alpine.store('app').sessionId;
    },

    get hasStory(): boolean {
      return !!this.sessionId || !!this.selectedStory;
    },

    get exportId(): string {
      return this.selectedStory || this.sessionId || '';
    },

    /** Title of the currently-active pipeline result, if any. */
    _resultTitle(): string {
      const r = Alpine.store('app').pipelineResult as { enhanced?: { title?: string }; draft?: { title?: string } } | null;
      return (r?.enhanced?.title || r?.draft?.title || '').trim();
    },

    /** Find checkpoint filename whose title matches the active pipeline result. */
    _matchCheckpointByTitle(): string {
      const title = this._resultTitle();
      if (!title) return '';
      const hit = this.stories.find(s => (s.title || '').trim() === title);
      return hit?.filename || '';
    },

    /** Resolve the story title for naming the downloaded file. */
    _downloadTitle(): string {
      if (this.selectedStory) {
        const hit = this.stories.find(s => s.filename === this.selectedStory);
        if (hit?.title) return hit.title;
      }
      const t = this._resultTitle();
      if (t) return t;
      return 'storyforge';
    },

    /** Windows-safe filename: strip reserved chars, trim, cap length. */
    _safeFilename(base: string, ext: string): string {
      const cleaned = base.replace(/[\\/:*?"<>|]+/g, '').replace(/\s+/g, ' ').trim();
      const out = (cleaned || 'storyforge').slice(0, 120);
      return `${out}.${ext}`;
    },

    async init(): Promise<void> {
      this.message = '';
      await this.loadStories();
      // If the in-memory session UUID may be stale (server restart / timeout),
      // auto-select the matching checkpoint so exports don't 404.
      if (!this.selectedStory && this.sessionId) {
        const match = this._matchCheckpointByTitle();
        if (match) this.selectedStory = match;
      }
    },

    async loadStories(): Promise<void> {
      this.loading = true;
      try {
        const resp = await API.get<{ items?: { filename: string; title: string; genre: string; chapter_count: number; modified: string }[] }>('/pipeline/stories?limit=50');
        this.stories = resp.items || [];
      } catch {
        this.stories = [];
      }
      this.loading = false;
    },

    /** Try /export/<format>/<id>; on 404 fall back to the matching checkpoint. */
    async _downloadWithFallback(format: string, filename: string): Promise<void> {
      try {
        await API.download(`/export/${format}/${encodeURIComponent(this.exportId)}`, filename);
        return;
      } catch (e) {
        const msg = (e as Error).message || '';
        const is404 = msg.includes('404');
        const usingSession = !this.selectedStory && !!this.sessionId;
        if (!is404 || !usingSession) throw e;
        const match = this._matchCheckpointByTitle();
        if (!match) throw e;
        this.selectedStory = match;
        await API.download(`/export/${format}/${encodeURIComponent(match)}`, filename);
      }
    },

    async exportFormat(format: string): Promise<void> {
      if (!this.exportId) {
        this.message = 'Vui lòng chọn truyện để xuất.';
        return;
      }
      this.exporting = format;
      this.message = '';
      try {
        const filename = this._safeFilename(this._downloadTitle(), format.toLowerCase());
        await this._downloadWithFallback(format, filename);
        this.message = `Xuất ${format.toUpperCase()} thành công!`;
        setTimeout(() => { if (!this.message.startsWith('Error')) this.message = ''; }, 5000);
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.exporting = null;
    },

    async exportZip(): Promise<void> {
      if (!this.exportId) {
        this.message = 'Vui lòng chọn truyện để xuất.';
        return;
      }
      this.exporting = 'zip';
      this.message = '';
      try {
        const filename = this._safeFilename(this._downloadTitle(), 'zip');
        await this._downloadWithFallback('zip', filename);
        this.message = 'Xuất ZIP thành công!';
        setTimeout(() => { if (!this.message.startsWith('Error')) this.message = ''; }, 5000);
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.exporting = null;
    },
  };
}

// ── forgeExportCards — M4-B3 (flag-gated) ────────────────────────────────────
//
// Visual selectable format cards (PDF/EPUB/HTML/ZIP). Selecting a card slides
// in a format-specific config panel. Falls through to exportPage() methods for
// actual export. Flag OFF = current export tiles remain untouched.
//
// Exported for unit testing.

export interface ForgeExportFormat {
  id: string;
  label: string;
  hint: string;
  color: string;
}

export const FORGE_EXPORT_FORMATS: ForgeExportFormat[] = [
  { id: 'pdf',  label: 'PDF',  hint: 'Print-ready · A4',      color: '#EF4444' },
  { id: 'epub', label: 'EPUB', hint: 'Kindle · digital read',  color: '#10B981' },
  { id: 'html', label: 'HTML', hint: 'Web · share online',     color: '#3B82F6' },
  { id: 'zip',  label: 'ZIP',  hint: 'Archive · all files',    color: '#8B5CF6' },
];

export interface ForgeExportCardsState {
  selectedFormat: string | null;
  panelVisible: boolean;
  formats: ForgeExportFormat[];
  selectFormat(id: string): void;
  closePanel(): void;
}

export function forgeExportCards(): ForgeExportCardsState {
  return {
    selectedFormat: null as string | null,
    panelVisible: false,
    formats: FORGE_EXPORT_FORMATS,

    selectFormat(id: string): void {
      if (this.selectedFormat === id) {
        this.panelVisible = !this.panelVisible;
      } else {
        this.selectedFormat = id;
        this.panelVisible = true;
      }
    },

    closePanel(): void {
      this.panelVisible = false;
      this.selectedFormat = null;
    },
  };
}
