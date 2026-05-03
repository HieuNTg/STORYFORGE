/**
 * Library page — browse saved stories and read inline.
 * Combines library (story list) + reader (chapter view) into one page.
 */

interface StoryCheckpoint {
  path: string;
  title?: string;
  genre?: string;
  chapter_count?: number;
  current_layer?: number;
  layer?: number;
  created_at?: string;
  modified?: string;
  size_kb?: number;
  [key: string]: unknown;
}

interface StoryChapter {
  title?: string;
  content?: string;
}

interface StoryContent {
  title?: string;
  genre?: string;
  chapters?: StoryChapter[];
}

interface LoadedStory {
  enhanced?: StoryContent;
  draft?: StoryContent;
  filename?: string;
}

interface CharacterProfile {
  name: string;
  frozen_prompt: string;
  prompt_version?: number | null;
  has_reference_image: boolean;
  reference_url?: string | null;
}

interface ChapterQuality {
  chapter_number: number;
  title: string;
  scoring_layer: number;
  scores: Record<string, number>;
  notes: string;
}

interface OverallQuality {
  scoring_layer: number;
  overall: number;
  avg_coherence: number;
  avg_character: number;
  avg_drama: number;
  avg_writing: number;
  weakest_chapter: number;
}

interface QualityResponse {
  overall: OverallQuality | null;
  chapters: ChapterQuality[];
}

function libraryPage() {
  return {
    // Library state
    stories: [] as StoryCheckpoint[],
    loading: false as boolean,
    error: '' as string,
    loadingStory: null as string | null,
    confirmDelete: null as string | null,
    searchQuery: '' as string,
    generatingImages: null as string | null,
    generatingChapterImage: null as number | null,
    rebuildingProfile: null as string | null,
    uploadingReference: null as string | null,
    imageStatus: '' as string,

    // Reader state
    selectedStory: null as LoadedStory | null,
    chapter: 0 as number,
    fontSize: 18 as number,
    characterProfiles: [] as CharacterProfile[],
    showCharacterPanel: false as boolean,
    qualityScores: null as QualityResponse | null,
    showQualityPanel: false as boolean,

    // Computed: current view mode
    get isReading(): boolean {
      return this.selectedStory !== null;
    },

    get story(): StoryContent | null {
      if (!this.selectedStory) return null;
      return this.selectedStory.enhanced || this.selectedStory.draft || null;
    },

    get chapters(): StoryChapter[] {
      if (!this.story) return [];
      return this.story.chapters || [];
    },

    get currentChapter(): StoryChapter | null {
      return this.chapters[this.chapter] || null;
    },

    get filteredStories(): StoryCheckpoint[] {
      if (!this.searchQuery) return this.stories;
      const q = this.searchQuery.toLowerCase();
      return this.stories.filter((s: StoryCheckpoint) =>
        (s.title || s.path).toLowerCase().includes(q) ||
        (s.genre || '').toLowerCase().includes(q)
      );
    },

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
        const data = await API.get<LoadedStory & { error?: string }>('/pipeline/checkpoints/' + encodeURIComponent(filename));
        if (data.error) {
          this.error = data.error;
          this.loadingStory = null;
          return;
        }
        // Set selected story for inline reading
        this.selectedStory = data;
        this.chapter = 0;
        this.characterProfiles = [];
        this.qualityScores = null;
        // Also update global stores for compatibility
        Alpine.store('pipeline').result = data;
        Alpine.store('pipeline').status = 'done';
        Alpine.store('pipeline').progress = 4;
        Alpine.store('app').pipelineResult = data;
        // Fire-and-forget: don't block reader render on profiles or quality
        this.loadCharacterProfiles(filename);
        this.loadQuality(filename);
      } catch (e) {
        this.error = 'Failed to load story: ' + (e as Error).message;
      }
      this.loadingStory = null;
    },

    async loadCharacterProfiles(filename: string): Promise<void> {
      try {
        const data = await API.get<{ profiles?: CharacterProfile[] }>(
          '/images/' + encodeURIComponent(filename) + '/profiles'
        );
        this.characterProfiles = data.profiles || [];
      } catch {
        this.characterProfiles = [];
      }
    },

    async loadQuality(filename: string): Promise<void> {
      try {
        const data = await API.get<QualityResponse>(
          '/quality/' + encodeURIComponent(filename)
        );
        this.qualityScores = data;
      } catch {
        // Older checkpoints / 404 → silently leave panel hidden.
        this.qualityScores = null;
      }
    },

    chapterScore(chapterNumber: number): ChapterQuality | null {
      const list = this.qualityScores?.chapters || [];
      return list.find((c) => c.chapter_number === chapterNumber) || null;
    },

    scoreColor(value: number): string {
      // 1-5 scale: ≥3.75 green, 2.5-3.75 amber, <2.5 red.
      if (value >= 3.75) return 'bg-emerald-100 text-emerald-700 border-emerald-200';
      if (value >= 2.5) return 'bg-amber-100 text-amber-700 border-amber-200';
      return 'bg-rose-100 text-rose-700 border-rose-200';
    },

    backToList(): void {
      this.selectedStory = null;
      this.chapter = 0;
      this.characterProfiles = [];
      this.showCharacterPanel = false;
      this.qualityScores = null;
      this.showQualityPanel = false;
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

    continueStory(story?: StoryCheckpoint): void {
      const s = story || (this.selectedStory ? {
        path: this.selectedStory.filename || '',
        title: this.story?.title || '',
        chapter_count: this.chapters.length,
        genre: this.story?.genre || '',
      } : null);
      if (!s) return;
      Alpine.store('pipeline').startContinuation({
        checkpoint: s.path,
        title: s.title || s.path,
        chapterCount: s.chapter_count || 0,
        genre: s.genre || '',
      });
      Alpine.store('app').navigate('pipeline');
    },

    async generateImages(story: StoryCheckpoint): Promise<void> {
      if (!story?.path) return;
      this.generatingImages = story.path;
      this.imageStatus = '';
      this.error = '';
      try {
        const data = await API.post<{ count: number; message: string; image_paths: string[]; chapter_images?: Record<string, string[]> }>(
          '/images/' + encodeURIComponent(story.path) + '/generate',
          {}
        );
        this.imageStatus = data.message || `Đã tạo ${data.count} ảnh`;
        // If we are currently reading this story, splice the new images onto loaded chapters.
        if (this.selectedStory && this.selectedStory.filename === story.path && data.chapter_images) {
          const map = data.chapter_images;
          const target = (this.selectedStory.enhanced || this.selectedStory.draft);
          target?.chapters?.forEach((ch: StoryChapter) => {
            const n = (ch as { chapter_number?: number }).chapter_number;
            if (n != null && map[String(n)]) {
              (ch as { images?: string[] }).images = map[String(n)];
            }
          });
        }
      } catch (e) {
        this.error = 'Tạo ảnh thất bại: ' + (e as Error).message;
      }
      this.generatingImages = null;
      setTimeout(() => { this.imageStatus = ''; }, 5000);
    },

    async generateChapterImage(chapterNumber: number): Promise<void> {
      // Reader-side regen: only the currently-loaded story's single chapter.
      const filename = this.selectedStory?.filename;
      if (!filename || chapterNumber == null) return;
      this.generatingChapterImage = chapterNumber;
      this.imageStatus = '';
      this.error = '';
      try {
        const data = await API.post<{ count: number; message: string; image_paths: string[]; chapter_images?: Record<string, string[]> }>(
          '/images/' + encodeURIComponent(filename) + '/generate',
          { chapter: chapterNumber }
        );
        this.imageStatus = data.message || `Đã tạo ${data.count} ảnh cho chương ${chapterNumber}`;
        const map = data.chapter_images || {};
        const target = (this.selectedStory?.enhanced || this.selectedStory?.draft);
        const ch = target?.chapters?.find((c: StoryChapter) =>
          (c as { chapter_number?: number }).chapter_number === chapterNumber
        );
        if (ch && map[String(chapterNumber)]) {
          (ch as { images?: string[] }).images = map[String(chapterNumber)];
        }
      } catch (e) {
        this.error = 'Tạo ảnh chương thất bại: ' + (e as Error).message;
      }
      this.generatingChapterImage = null;
      setTimeout(() => { this.imageStatus = ''; }, 5000);
    },

    async rebuildCharacterProfile(name: string): Promise<void> {
      const filename = this.selectedStory?.filename;
      if (!filename || !name || this.rebuildingProfile) return;
      this.rebuildingProfile = name;
      this.error = '';
      try {
        const data = await API.post<CharacterProfile & { rebuilt: boolean }>(
          '/images/' + encodeURIComponent(filename) +
            '/profiles/' + encodeURIComponent(name) + '/rebuild',
          {}
        );
        const idx = this.characterProfiles.findIndex((p) => p.name === data.name);
        const next: CharacterProfile = {
          name: data.name,
          frozen_prompt: data.frozen_prompt,
          prompt_version: data.prompt_version,
          has_reference_image: data.has_reference_image,
          reference_url: data.reference_url,
        };
        if (idx >= 0) this.characterProfiles.splice(idx, 1, next);
        else this.characterProfiles.push(next);
      } catch (e) {
        this.error = 'Tạo lại hồ sơ thất bại: ' + (e as Error).message;
      }
      this.rebuildingProfile = null;
    },

    async uploadReference(name: string, file: File | null): Promise<void> {
      const filename = this.selectedStory?.filename;
      if (!filename || !name || !file || this.uploadingReference) return;
      this.uploadingReference = name;
      this.error = '';
      try {
        const form = new FormData();
        form.append('file', file);
        const csrf = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
        const headers: Record<string, string> = {};
        if (csrf) headers['X-CSRF-Token'] = decodeURIComponent(csrf[1]);
        const res = await fetch(
          '/api/images/' + encodeURIComponent(filename) +
            '/profiles/' + encodeURIComponent(name) + '/reference',
          { method: 'POST', headers, body: form },
        );
        if (!res.ok) {
          let detail = `Upload: ${res.status}`;
          try { const body = await res.json(); if (body.detail) detail = body.detail; } catch { /* ignore */ }
          throw new Error(detail);
        }
        const data = await res.json() as CharacterProfile;
        const idx = this.characterProfiles.findIndex((p) => p.name === data.name);
        const next: CharacterProfile = {
          name: data.name,
          frozen_prompt: data.frozen_prompt,
          prompt_version: data.prompt_version,
          has_reference_image: data.has_reference_image,
          reference_url: data.reference_url,
        };
        if (idx >= 0) this.characterProfiles.splice(idx, 1, next);
        else this.characterProfiles.push(next);
      } catch (e) {
        this.error = 'Tải ảnh tham chiếu thất bại: ' + (e as Error).message;
      }
      this.uploadingReference = null;
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

    // Reader navigation
    prev(): void { if (this.chapter > 0) this.chapter--; },
    next(): void { if (this.chapter < this.chapters.length - 1) this.chapter++; },
  };
}
