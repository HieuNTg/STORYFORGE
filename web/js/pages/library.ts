/**
 * Library page — browse and load saved stories from checkpoints.
 */

interface StoryCheckpoint {
  path: string;
  title?: string;
  layer?: number;
  created_at?: string;
  [key: string]: unknown;
}

function libraryPage() {
  return {
    stories: [] as StoryCheckpoint[],
    loading: false as boolean,
    error: '' as string,
    loadingStory: null as string | null,
    confirmDelete: null as string | null,

    init(): void {
      this.loadStories();
    },

    async loadStories(): Promise<void> {
      this.loading = true;
      this.error = '';
      try {
        const data = await API.get<{ checkpoints?: StoryCheckpoint[] }>('/pipeline/checkpoints');
        this.stories = data.checkpoints || [];
      } catch (e) {
        this.error = 'Failed to load stories: ' + (e as Error).message;
        this.stories = [];
      }
      this.loading = false;
    },

    async openStory(filename: string): Promise<void> {
      this.loadingStory = filename;
      this.error = '';
      try {
        const data = await API.get<{ error?: string }>('/pipeline/checkpoints/' + encodeURIComponent(filename));
        if (data.error) {
          this.error = data.error;
          this.loadingStory = null;
          return;
        }
        // Load into pipeline store and navigate to reader
        Alpine.store('pipeline').result = data;
        Alpine.store('pipeline').status = 'done';
        Alpine.store('pipeline').progress = 4;
        Alpine.store('app').pipelineResult = data;
        Alpine.store('app').navigate('reader');
      } catch (e) {
        this.error = 'Failed to load story: ' + (e as Error).message;
      }
      this.loadingStory = null;
    },

    async deleteStory(filename: string): Promise<void> {
      this.error = '';
      try {
        const data = await API.del<{ error?: string }>('/pipeline/checkpoints/' + encodeURIComponent(filename));
        if (data.error) {
          this.error = data.error;
        } else {
          this.stories = this.stories.filter((s: StoryCheckpoint) => s.path !== filename);
        }
      } catch (e) {
        this.error = 'Failed to delete: ' + (e as Error).message;
      }
      this.confirmDelete = null;
    },

    layerLabel(layer: number): string {
      const labels: Record<number, string> = { 1: 'Draft', 2: 'Enhanced', 3: 'Complete' };
      return labels[layer] || 'Draft';
    },

    layerColor(layer: number): string {
      if (layer >= 3) return 'bg-green-100 text-green-700';
      if (layer === 2) return 'bg-blue-100 text-blue-700';
      return 'bg-amber-100 text-amber-700';
    },
  };
}
