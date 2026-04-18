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

    async init(): Promise<void> {
      this.message = '';
      await this.loadStories();
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

    async exportFormat(format: string): Promise<void> {
      if (!this.exportId) {
        this.message = 'Vui lòng chọn truyện để xuất.';
        return;
      }
      this.exporting = format;
      this.message = '';
      try {
        const filename = 'storyforge.' + format.toLowerCase();
        await API.download(`/export/${format}/${encodeURIComponent(this.exportId)}`, filename);
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
        await API.download(`/export/zip/${encodeURIComponent(this.exportId)}`, 'storyforge_export.zip');
        this.message = 'Xuất ZIP thành công!';
        setTimeout(() => { if (!this.message.startsWith('Error')) this.message = ''; }, 5000);
      } catch (e) {
        this.message = 'Error: ' + (e as Error).message;
      }
      this.exporting = null;
    },
  };
}
