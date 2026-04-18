/**
 * Gallery page — browse and share public stories.
 */

interface GalleryItem {
  share_id: string;
  story_title: string;
  created_at: string;
  expires_at: string;
}

interface GalleryResponse {
  items: GalleryItem[];
  total: number;
  limit: number;
  offset: number;
}

interface SavedStory {
  filename: string;
  title: string;
  genre: string;
  chapter_count: number;
}

function galleryPage() {
  return {
    items: [] as GalleryItem[],
    total: 0,
    loading: false,
    error: '',
    offset: 0,
    limit: 20,

    // Share dialog
    showShareDialog: false,
    shareSessionId: '',
    sharePublic: true,
    shareExpiresDays: 30,
    shareLoading: false,
    shareResult: null as { share_id: string; story_title: string } | null,
    shareError: '',

    // Available stories for selection
    availableStories: [] as SavedStory[],
    loadingStories: false,

    async init(): Promise<void> {
      await this.loadGallery();
    },

    async loadGallery(): Promise<void> {
      this.loading = true;
      this.error = '';
      try {
        const res: GalleryResponse = await API.get(`/share/gallery?limit=${this.limit}&offset=${this.offset}`);
        this.items = res.items || [];
        this.total = res.total || 0;
      } catch (e) {
        this.error = e instanceof Error ? e.message : 'Failed to load gallery';
      } finally {
        this.loading = false;
      }
    },

    async nextPage(): Promise<void> {
      if (this.offset + this.limit < this.total) {
        this.offset += this.limit;
        await this.loadGallery();
      }
    },

    async prevPage(): Promise<void> {
      if (this.offset > 0) {
        this.offset = Math.max(0, this.offset - this.limit);
        await this.loadGallery();
      }
    },

    openShare(share_id: string): void {
      window.open(`/api/share/${share_id}`, '_blank');
    },

    formatDate(iso: string): string {
      if (!iso) return '';
      const d = new Date(iso);
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    },

    daysUntilExpiry(expires_at: string): number {
      if (!expires_at) return 0;
      const now = Date.now();
      const exp = new Date(expires_at).getTime();
      return Math.max(0, Math.ceil((exp - now) / (1000 * 60 * 60 * 24)));
    },

    // Share dialog methods
    async openShareDialog(): Promise<void> {
      this.shareSessionId = '';
      this.shareResult = null;
      this.shareError = '';
      this.showShareDialog = true;
      await this.loadAvailableStories();
    },

    async loadAvailableStories(): Promise<void> {
      this.loadingStories = true;
      try {
        const res = await API.get<{ items: SavedStory[] }>('/pipeline/stories?limit=50');
        this.availableStories = res.items || [];
        if (this.availableStories.length > 0 && !this.shareSessionId) {
          this.shareSessionId = this.availableStories[0].filename;
        }
      } catch {
        this.availableStories = [];
      } finally {
        this.loadingStories = false;
      }
    },

    async createShare(): Promise<void> {
      if (!this.shareSessionId) {
        this.shareError = 'No active session to share';
        return;
      }
      this.shareLoading = true;
      this.shareError = '';
      try {
        const res = await API.post<{ share_id: string; story_title: string; error?: string }>('/share/create', {
          session_id: this.shareSessionId,
          is_public: this.sharePublic,
          expires_days: this.shareExpiresDays,
        });
        if (res.error) {
          this.shareError = res.error;
        } else {
          this.shareResult = { share_id: res.share_id, story_title: res.story_title };
          await this.loadGallery();
        }
      } catch (e) {
        this.shareError = e instanceof Error ? e.message : 'Share failed';
      } finally {
        this.shareLoading = false;
      }
    },

    copyShareLink(): void {
      if (!this.shareResult) return;
      const url = `${window.location.origin}/api/share/${this.shareResult.share_id}`;
      navigator.clipboard.writeText(url);
    },

    async deleteShare(share_id: string): Promise<void> {
      if (!confirm('Delete this shared story?')) return;
      try {
        await API.del(`/share/${share_id}`);
        await this.loadGallery();
      } catch (e) {
        alert(e instanceof Error ? e.message : 'Delete failed');
      }
    },
  };
}
