/**
 * Library page — browse and load saved stories from checkpoints.
 */
function libraryPage() {
  return {
    stories: [],
    loading: false,
    error: '',
    loadingStory: null,
    confirmDelete: null,

    init() {
      this.loadStories();
    },

    async loadStories() {
      this.loading = true;
      this.error = '';
      try {
        const data = await API.get('/pipeline/checkpoints');
        this.stories = data.checkpoints || [];
      } catch (e) {
        this.error = 'Failed to load stories: ' + e.message;
        this.stories = [];
      }
      this.loading = false;
    },

    async openStory(filename) {
      this.loadingStory = filename;
      this.error = '';
      try {
        const data = await API.get('/pipeline/checkpoints/' + encodeURIComponent(filename));
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
        this.error = 'Failed to load story: ' + e.message;
      }
      this.loadingStory = null;
    },

    async deleteStory(filename) {
      this.error = '';
      try {
        const data = await API.del('/pipeline/checkpoints/' + encodeURIComponent(filename));
        if (data.error) {
          this.error = data.error;
        } else {
          this.stories = this.stories.filter(s => s.path !== filename);
        }
      } catch (e) {
        this.error = 'Failed to delete: ' + e.message;
      }
      this.confirmDelete = null;
    },

    layerLabel(layer) {
      const labels = { 1: 'Draft', 2: 'Enhanced', 3: 'Complete' };
      return labels[layer] || 'Draft';
    },

    layerColor(layer) {
      if (layer >= 3) return 'bg-green-100 text-green-700';
      if (layer === 2) return 'bg-blue-100 text-blue-700';
      return 'bg-amber-100 text-amber-700';
    },
  };
}
