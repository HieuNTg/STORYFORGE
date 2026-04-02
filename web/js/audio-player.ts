/**
 * audioPlayer — Alpine.js component for TTS story playback.
 * Register: Alpine.data('audioPlayer', audioPlayer)
 */

interface ChapterData {
  content: string;
  title?: string;
  [key: string]: unknown;
}

interface AudioStatusResponse {
  exists: boolean;
  audio_url: string;
}

interface AudioGenerateResponse {
  audio_url: string;
  error?: string;
}

function audioPlayer() {
  return {
    // State
    visible: false as boolean,
    playing: false as boolean,
    loading: false as boolean,
    error: '' as string,
    currentChapter: 0 as number,
    progress: 0 as number,
    duration: 0 as number,
    playbackRate: 1 as number,
    audioCache: {} as Record<number, string>, // chapter_index -> audio_url

    // Internal
    _audio: null as HTMLAudioElement | null,

    get chapters(): ChapterData[] {
      const result = Alpine.store('app').pipelineResult;
      if (!result) return [];
      const story = result.enhanced || result.draft || null;
      return story ? (story.chapters || []) : [];
    },

    get currentChapterData(): ChapterData | null {
      return this.chapters[this.currentChapter] || null;
    },

    get progressPercent(): number {
      if (!this.duration) return 0;
      return Math.round((this.progress / this.duration) * 100);
    },

    get timeDisplay(): string {
      const fmt = (s: number): string => {
        const m = Math.floor(s / 60);
        return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
      };
      return `${fmt(this.progress)} / ${fmt(this.duration)}`;
    },

    _initAudio(): void {
      if (this._audio) return;
      this._audio = new Audio();
      this._audio.onended = () => this._onEnded();
      this._audio.ontimeupdate = () => {
        this.progress = this._audio!.currentTime;
        this.duration = this._audio!.duration || 0;
      };
      this._audio.onplay = () => { this.playing = true; };
      this._audio.onpause = () => { this.playing = false; };
      this._audio.onerror = () => {
        this.error = 'Audio playback error';
        this.playing = false;
        this.loading = false;
      };
    },

    async generateAudio(chapterIndex: number): Promise<string | null> {
      const ch: ChapterData | undefined = this.chapters[chapterIndex];
      if (!ch) return null;
      if (this.audioCache[chapterIndex]) return this.audioCache[chapterIndex];

      this.loading = true;
      this.error = '';
      try {
        const res = await fetch(`/api/audio/generate/${chapterIndex}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: ch.content }),
        });
        const data: AudioGenerateResponse = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Generation failed');
        this.audioCache[chapterIndex] = data.audio_url;
        return data.audio_url;
      } catch (e) {
        this.error = (e as Error).message;
        return null;
      } finally {
        this.loading = false;
      }
    },

    async play(chapterIndex?: number): Promise<void> {
      const idx = chapterIndex ?? this.currentChapter;
      this._initAudio();

      // Check if already cached
      let url: string | undefined = this.audioCache[idx];
      if (!url) {
        // Check server-side status first
        try {
          const res = await fetch(`/api/audio/status/${idx}`);
          const data: AudioStatusResponse = await res.json();
          if (data.exists) url = data.audio_url;
        } catch (_) {}
      }
      if (!url) url = await this.generateAudio(idx) ?? undefined;
      if (!url) return;

      this.currentChapter = idx;
      this._audio!.src = url;
      this._audio!.playbackRate = this.playbackRate;
      this._audio!.play().catch((e: Error) => { this.error = e.message; });
    },

    pause(): void {
      this._audio?.pause();
    },

    toggle(): void {
      if (!this._audio || !this._audio.src) { this.play(); return; }
      if (this.playing) this.pause(); else this._audio.play();
    },

    async skip(delta: number): Promise<void> {
      const next = this.currentChapter + delta;
      if (next < 0 || next >= this.chapters.length) return;
      if (this._audio) this._audio.pause();
      await this.play(next);
    },

    seek(e: MouseEvent): void {
      if (!this._audio || !this.duration) return;
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      this._audio.currentTime = ratio * this.duration;
    },

    setRate(rate: number | string): void {
      this.playbackRate = parseFloat(rate as string);
      if (this._audio) this._audio.playbackRate = this.playbackRate;
    },

    _onEnded(): void {
      this.playing = false;
      // Auto-advance
      const next = this.currentChapter + 1;
      if (next < this.chapters.length) this.play(next);
    },

    destroy(): void {
      if (this._audio) { this._audio.pause(); this._audio = null; }
    },
  };
}
