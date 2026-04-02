/**
 * Export page — download story in various formats.
 */
function exportPage() {
  return {
    exporting: null as string | null,
    message: '' as string,

    get sessionId(): string | null {
      return Alpine.store('app').sessionId;
    },

    get hasStory(): boolean {
      return !!this.sessionId;
    },

    init(): void {
      // Clear stale message on page mount
      this.message = '';
    },

    async exportFormat(format: string): Promise<void> {
      if (!this.sessionId) {
        this.message = 'No story yet. Run the pipeline first.';
        return;
      }
      this.exporting = format;
      this.message = '';
      try {
        const filename = 'storyforge.' + format.toLowerCase();
        await API.download(`/export/${format}/${this.sessionId}`, filename);
        this.message = `${format} downloaded successfully!`;
        // Auto-clear success message after 5s
        setTimeout(() => { if (!this.message.startsWith('Error')) this.message = ''; }, 5000);
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.exporting = null;
    },

    async exportZip(): Promise<void> {
      if (!this.sessionId) {
        this.message = 'No story yet.';
        return;
      }
      this.exporting = 'zip';
      this.message = '';
      try {
        await API.download(`/export/zip/${this.sessionId}`, 'storyforge_export.zip');
        this.message = 'ZIP downloaded successfully!';
        setTimeout(() => { if (!this.message.startsWith('Error')) this.message = ''; }, 5000);
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.exporting = null;
    },
  };
}
