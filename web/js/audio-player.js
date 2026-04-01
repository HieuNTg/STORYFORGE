/**
 * audioPlayer — Alpine.js component for TTS story playback.
 * Register: Alpine.data('audioPlayer', audioPlayer)
 */
function audioPlayer() {
  return {
    // State
    visible: false,
    playing: false,
    loading: false,
    error: '',
    currentChapter: 0,
    progress: 0,
    duration: 0,
    playbackRate: 1,
    audioCache: {}, // chapter_index -> audio_url

    // Internal
    _audio: null,

    get chapters() {
      const result = Alpine.store('app').pipelineResult;
      if (!result) return [];
      const story = result.enhanced || result.draft || null;
      return story ? (story.chapters || []) : [];
    },

    get currentChapterData() {
      return this.chapters[this.currentChapter] || null;
    },

    get progressPercent() {
      if (!this.duration) return 0;
      return Math.round((this.progress / this.duration) * 100);
    },

    get timeDisplay() {
      const fmt = (s) => {
        const m = Math.floor(s / 60);
        return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
      };
      return `${fmt(this.progress)} / ${fmt(this.duration)}`;
    },

    _initAudio() {
      if (this._audio) return;
      this._audio = new Audio();
      this._audio.onended = () => this._onEnded();
      this._audio.ontimeupdate = () => {
        this.progress = this._audio.currentTime;
        this.duration = this._audio.duration || 0;
      };
      this._audio.onplay = () => { this.playing = true; };
      this._audio.onpause = () => { this.playing = false; };
      this._audio.onerror = () => {
        this.error = 'Audio playback error';
        this.playing = false;
        this.loading = false;
      };
    },

    async generateAudio(chapterIndex) {
      const ch = this.chapters[chapterIndex];
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
        const data = await res.json();
        if (!res.ok || data.error) throw new Error(data.error || 'Generation failed');
        this.audioCache[chapterIndex] = data.audio_url;
        return data.audio_url;
      } catch (e) {
        this.error = e.message;
        return null;
      } finally {
        this.loading = false;
      }
    },

    async play(chapterIndex) {
      const idx = chapterIndex ?? this.currentChapter;
      this._initAudio();

      // Check if already cached
      let url = this.audioCache[idx];
      if (!url) {
        // Check server-side status first
        try {
          const res = await fetch(`/api/audio/status/${idx}`);
          const data = await res.json();
          if (data.exists) url = data.audio_url;
        } catch (_) {}
      }
      if (!url) url = await this.generateAudio(idx);
      if (!url) return;

      this.currentChapter = idx;
      this._audio.src = url;
      this._audio.playbackRate = this.playbackRate;
      this._audio.play().catch((e) => { this.error = e.message; });
    },

    pause() {
      this._audio?.pause();
    },

    toggle() {
      if (!this._audio || !this._audio.src) { this.play(); return; }
      if (this.playing) this.pause(); else this._audio.play();
    },

    async skip(delta) {
      const next = this.currentChapter + delta;
      if (next < 0 || next >= this.chapters.length) return;
      if (this._audio) this._audio.pause();
      await this.play(next);
    },

    seek(e) {
      if (!this._audio || !this.duration) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      this._audio.currentTime = ratio * this.duration;
    },

    setRate(rate) {
      this.playbackRate = parseFloat(rate);
      if (this._audio) this._audio.playbackRate = this.playbackRate;
    },

    _onEnded() {
      this.playing = false;
      // Auto-advance
      const next = this.currentChapter + 1;
      if (next < this.chapters.length) this.play(next);
    },

    destroy() {
      if (this._audio) { this._audio.pause(); this._audio = null; }
    },
  };
}
