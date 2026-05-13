/**
 * pipeline store — pipeline status, progress, SSE streaming, continuation modes.
 *
 * Extracted from app.ts. Store key: 'pipeline'.
 * Behavior is identical to the original inline definition.
 * SSE event shape is unchanged per §4.5 of the engineering plan.
 */

type PipelineStatus = 'idle' | 'running' | 'done' | 'error' | 'interrupted';

interface PipelineForm {
  title: string;
  genre: string;
  style: string;
  language: string;
  idea: string;
  num_chapters: number;
  num_characters: number;
  word_count: number;
  num_sim_rounds: number;
  drama_level: string;
  shots_per_chapter: number;
  enable_agents: boolean;
  enable_scoring: boolean;
  enable_media: boolean;
  enable_l1_consistency: boolean;
  // Advanced L1 settings
  enable_emotional_memory: boolean;
  enable_scene_beat_writing: boolean;
  enable_l1_causal_graph: boolean;
  enable_self_review: boolean;
  enable_agent_debate: boolean;
  // Advanced L2 settings
  l2_drama_threshold: number;
  l2_drama_target: number;
  // Quality settings
  enable_quality_gate: boolean;
  quality_gate_threshold: number;
  enable_smart_revision: boolean;
  smart_revision_threshold: number;
  [key: string]: unknown;
}

interface PipelineResult {
  session_id?: string;
  livePreview?: string;
  filename?: string;
  [key: string]: unknown;
}

interface CheckpointItem {
  path: string;
  [key: string]: unknown;
}

interface GenreChoicesResponse {
  genres?: string[];
  styles?: string[];
  drama_levels?: string[];
}

export function createPipelineStore() {
  return {
    status: 'idle' as PipelineStatus,
    currentLog: '' as string,
    logs: [] as string[],
    livePreview: '' as string,
    progress: 0,
    result: null as PipelineResult | null,
    error: null as string | null,
    checkpoints: [] as CheckpointItem[],

    continuationMode: false as boolean,
    continuationMeta: null as {
      checkpoint: string;
      title: string;
      chapterCount: number;
      genre: string;
      resumeFromChapter?: number;
      targetChapters?: number;
      interruptedAt?: string;
    } | null,

    runStartedAt: null as number | null,
    runFinishedAt: null as number | null,

    pendingJumpAfterOpen: false as boolean,

    multiPathMode: false as boolean,
    paths: [] as Array<{ id: string; title: string; summary: string; outlines: Array<{ chapter_number: number; title: string; summary: string; key_events: string[] }> }>,
    selectedPathId: null as string | null,

    collaborativeMode: false as boolean,
    collaborativeText: '' as string,
    collaborativeChapterNum: 1 as number,
    collaborativeTitle: '' as string,
    polishLevel: 'light' as 'light' | 'medium' | 'heavy',
    polishedResult: null as { title: string; content: string; word_count: number } | null,

    consistencyMode: false as boolean,
    consistencyReport: null as { issues: Array<{ severity: string; category: string; description: string; suggestion: string; chapter_refs: number[] }>; error_count: number; warning_count: number; is_consistent: boolean } | null,

    outlineMode: false as boolean,
    outlines: [] as Array<{ chapter_number: number; title: string; summary: string; key_events: string[]; scenes: Array<{ beat: string; characters: string[]; location: string }> }>,
    editingOutlineIdx: null as number | null,

    form: {
      title: '', genre: 'Tiên Hiệp', style: 'Miêu tả chi tiết', language: 'vi',
      idea: '', num_chapters: 5, num_characters: 5, word_count: 2000,
      num_sim_rounds: 3, drama_level: 'cao', shots_per_chapter: 8,
      enable_agents: true, enable_scoring: true, enable_media: false,
      lite_mode: false,
      enable_l1_consistency: false,
      enable_emotional_memory: true,
      enable_proactive_constraints: true,
      enable_thread_enforcement: true,
      enable_emotional_bridge: true,
      enable_scene_beat_writing: true,
      enable_l1_causal_graph: true,
      enable_self_review: true,
      enable_agent_debate: true,
      l2_drama_threshold: 0.5,
      l2_drama_target: 0.65,
      enable_quality_gate: true,
      quality_gate_threshold: 2.5,
      enable_smart_revision: true,
      smart_revision_threshold: 3.5,
    } as PipelineForm,

    genres: [] as string[], styles: [] as string[], dramaLevels: [] as string[],
    languages: [
      { code: 'vi', name: 'Tiếng Việt' },
      { code: 'en', name: 'English' },
      { code: 'zh', name: '中文' },
    ] as Array<{ code: string; name: string }>,
    templates: {} as Record<string, unknown>,

    async loadChoices(): Promise<void> {
      try {
        const data = await API.get<GenreChoicesResponse>('/pipeline/genres');
        this.genres = data.genres || [];
        this.styles = data.styles || [];
        this.dramaLevels = data.drama_levels || [];
      } catch (e) { console.error('Load choices failed:', e); }
    },

    async loadTemplates(): Promise<void> {
      try {
        this.templates = await API.get<Record<string, unknown>>('/pipeline/templates');
      } catch (e) { console.error('Load templates failed:', e); }
    },

    async _streamPipeline(url: string, body: Record<string, unknown>): Promise<void> {
      this.status = 'running';
      this.logs = [];
      this.livePreview = '';
      this.progress = 0;
      this.result = null;
      this.error = null;
      this.runStartedAt = Date.now();
      this.runFinishedAt = null;

      // SSE → Toast bridge (additive). Tracks the prior progress so we only
      // emit a "phase change" toast on the L1→L2 transition (1 → 2). All
      // emit calls are no-ops when the Forge flag is off (toast store absent).
      let lastPhase = 0;
      this._emitToast('info', 'Generation started');

      try {
        for await (const event of API.stream(url, body)) {
          if (event.type === 'session') {
            Alpine.store('app').sessionId = event.session_id ?? null;
          } else if (event.type === 'log') {
            this.currentLog = event.data as string;
            this.logs.push(event.data as string);
            const nextPhase = this._detectLayer(event.data as string);
            this.progress = nextPhase;
            if (lastPhase === 1 && nextPhase === 2) {
              this._emitToast('info', 'Layer 2: enhancement starting');
            }
            const chapterTitle = this._sniffChapterCompletion(event.data as string);
            if (chapterTitle) {
              this._emitToast('success', `Chapter complete: ${chapterTitle}`);
            }
            lastPhase = nextPhase;
          } else if (event.type === 'stream') {
            this.livePreview = event.data as string;
          } else if (event.type === 'done') {
            const result = event.data as PipelineResult;
            this.result = result;
            Alpine.store('app').savePipelineResult(result);
            Alpine.store('app').sessionId = result.session_id ?? null;
            this.status = 'done';
            this.progress = 4;
            this.runFinishedAt = Date.now();
            // Sticky success — user must acknowledge.
            this._emitToast('success', 'Generation complete', 0);
          } else if (event.type === 'error') {
            this.error = event.data as string;
            this.status = 'error';
            this._emitToast('error', (event.data as string) || 'Generation failed');
          } else if (event.type === 'interrupted') {
            this.error = 'Connection lost. You can resume from the last checkpoint.';
            this.status = 'interrupted';
            this._emitToast('warning', 'Connection lost — resume from checkpoint available');
          }
        }
        if (this.status === 'running') {
          this.status = 'done';
          this.runFinishedAt = Date.now();
        }
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
        this._emitToast('error', (e as Error).message || 'Pipeline failed');
      }
    },

    // Best-effort chapter-complete detector. Matches "Chương N: <title>" — the
    // shape the L1 chapter_writer emits on completion. Returns null when the
    // log line isn't a chapter completion notice. Pure-function: kept here so
    // unit tests can exercise it directly through the store factory.
    //
    // Canonical regex: shared with web/js/stores/sse-sniffers.ts —
    // sniffChapterCompletion(). Keep both in sync if you change either.
    _sniffChapterCompletion(msg: string): string | null {
      // Examples: "✅ Chương 3: Đại Đạo Triều Thiên" or "✅ Chapter 3: ...".
      const m = msg.match(/^(?:✅\s*)?(?:Chương|Chapter)\s+(\d+):\s*(.+?)\s*$/);
      if (!m) return null;
      const title = (m[2] || '').replace(/\s+/g, ' ').trim();
      return title.length > 0 ? `Ch. ${m[1]} — ${title}` : `Ch. ${m[1]}`;
    },

    // Push to the Forge toast store when the flag-gated store is registered.
    // Silent no-op otherwise — keeps legacy callers byte-identical.
    _emitToast(
      variant: 'info' | 'success' | 'warning' | 'error',
      message: string,
      durationMs?: number,
    ): void {
      try {
        const store = (typeof Alpine !== 'undefined'
          ? (Alpine as unknown as { store: (k: string) => unknown }).store('toasts')
          : null) as { push?: (i: { message: string; variant: string; durationMs?: number }) => string } | null;
        if (!store || typeof store.push !== 'function') return;
        store.push({ message, variant, durationMs });
      } catch {
        // Never let a toast error break the SSE pipeline. Diagnostic only.
      }
    },

    async run(): Promise<void> {
      const idea = (this.form.idea || '').trim();
      if (!idea || idea.length < 10) {
        this.error = 'Please enter a story idea (at least 10 characters).';
        this.status = 'error';
        return;
      }
      await this._streamPipeline('/pipeline/run', this.form as PipelineForm & Record<string, unknown>);
    },

    startContinuation(meta: {
      checkpoint: string;
      title: string;
      chapterCount: number;
      genre: string;
      resumeFromChapter?: number;
      targetChapters?: number;
      interruptedAt?: string;
    }): void {
      this.continuationMode = true;
      this.continuationMeta = meta;
      this.status = 'idle';
      this.result = null;
      this.error = null;
      this.logs = [];
      this.livePreview = '';
      this.progress = 0;
    },

    async runContinuation(): Promise<void> {
      if (!this.continuationMeta) return;
      await this._streamPipeline('/pipeline/continue', {
        checkpoint: this.continuationMeta.checkpoint,
        additional_chapters: this.form.num_chapters,
        word_count: this.form.word_count,
        style: this.form.style,
        run_enhancement: this.form.enable_agents,
        num_sim_rounds: this.form.num_sim_rounds,
      });
    },

    async loadCheckpoints(): Promise<void> {
      try {
        const data = await API.get<{ checkpoints?: CheckpointItem[] }>('/pipeline/checkpoints');
        this.checkpoints = data.checkpoints || [];
      } catch (e) {
        console.error('Load checkpoints failed:', e);
        this.checkpoints = [];
      }
    },

    async resumeFromCheckpoint(path: string): Promise<void> {
      await this._streamPipeline('/pipeline/resume', { checkpoint: path });
    },

    _detectLayer(msg: string): number {
      const up = msg.toUpperCase();
      if (up.includes('MEDIA') || up.includes('IMAGE')) return 3;
      if (up.includes('LAYER 2') || up.includes('MÔ PHỎNG') || up.includes('ENHANCE')) return 2;
      if (up.includes('LAYER 1') || up.includes('TẠO TRUYỆN') || up.includes('CHƯƠNG')) return 1;
      return this.progress || 0;
    },

    async generatePaths(numPaths: number = 3): Promise<void> {
      if (!this.continuationMeta) return;
      this.status = 'running';
      this.error = null;
      this.paths = [];
      try {
        const data = await API.post<{ paths: Array<{ id: string; title: string; summary: string; outlines: Array<{ chapter_number: number; title: string; summary: string; key_events: string[] }> }> }>('/pipeline/continue/paths', {
          checkpoint: this.continuationMeta.checkpoint,
          additional_chapters: this.form.num_chapters,
          num_paths: numPaths,
        });
        this.paths = data.paths || [];
        this.multiPathMode = true;
        this.status = 'idle';
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    async selectPath(pathId: string): Promise<void> {
      const path = this.paths.find(p => p.id === pathId);
      if (!path || !this.continuationMeta) return;
      this.selectedPathId = pathId;
      await this._streamPipeline('/pipeline/continue/select-path', {
        checkpoint: this.continuationMeta.checkpoint,
        path_id: pathId,
        outlines: path.outlines,
        word_count: this.form.word_count,
        style: this.form.style,
      });
      this.multiPathMode = false;
      this.paths = [];
    },

    async generateOutlines(): Promise<void> {
      if (!this.continuationMeta) return;
      this.status = 'running';
      this.error = null;
      try {
        const data = await API.post<{ outlines: Array<{ chapter_number: number; title: string; summary: string; key_events: string[]; scenes: Array<{ beat: string; characters: string[]; location: string }> }> }>('/pipeline/continue/outlines', {
          checkpoint: this.continuationMeta.checkpoint,
          additional_chapters: this.form.num_chapters,
        });
        this.outlines = data.outlines || [];
        this.outlineMode = true;
        this.status = 'idle';
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    async writeFromOutlines(): Promise<void> {
      if (!this.continuationMeta || this.outlines.length === 0) return;
      await this._streamPipeline('/pipeline/continue/write', {
        checkpoint: this.continuationMeta.checkpoint,
        outlines: this.outlines,
        word_count: this.form.word_count,
        style: this.form.style,
      });
      this.outlineMode = false;
      this.outlines = [];
    },

    async polishChapter(): Promise<void> {
      if (!this.continuationMeta || !this.collaborativeText.trim()) return;
      this.status = 'running';
      this.error = null;
      this.polishedResult = null;
      try {
        for await (const event of API.stream('/pipeline/collaborative-chapter', {
          checkpoint: this.continuationMeta.checkpoint,
          chapter_number: this.collaborativeChapterNum,
          user_text: this.collaborativeText,
          title: this.collaborativeTitle,
          polish_level: this.polishLevel,
        })) {
          if (event.type === 'progress') {
            this.currentLog = event.data as string;
            this.logs.push(event.data as string);
          } else if (event.type === 'done') {
            const result = event.data as { title: string; content: string; word_count: number };
            this.polishedResult = result;
            this.status = 'done';
          } else if (event.type === 'error') {
            this.error = event.data as string;
            this.status = 'error';
          }
        }
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    async checkConsistency(chapterNumbers?: number[]): Promise<void> {
      if (!this.continuationMeta) return;
      this.status = 'running';
      this.error = null;
      this.consistencyReport = null;
      try {
        for await (const event of API.stream('/pipeline/check-consistency', {
          checkpoint: this.continuationMeta.checkpoint,
          chapter_numbers: chapterNumbers || [],
        })) {
          if (event.type === 'progress') {
            this.currentLog = event.data as string;
            this.logs.push(event.data as string);
          } else if (event.type === 'done') {
            this.consistencyReport = event.data as typeof this.consistencyReport;
            this.consistencyMode = true;
            this.status = 'done';
          } else if (event.type === 'error') {
            this.error = event.data as string;
            this.status = 'error';
          }
        }
      } catch (e) {
        this.error = (e as Error).message;
        this.status = 'error';
      }
    },

    dismissContinuationCallout(): void {
      this.continuationMode = false;
      this.continuationMeta = null;
    },

    clearResumeRibbon(): void {
      this.continuationMeta = null;
    },

    reset(): void {
      this.status = 'idle';
      this.logs = [];
      this.livePreview = '';
      this.progress = 0;
      this.result = null;
      this.error = null;
      this.checkpoints = [];
      this.continuationMode = false;
      this.continuationMeta = null;
      this.runStartedAt = null;
      this.runFinishedAt = null;
      this.pendingJumpAfterOpen = false;
      this.multiPathMode = false;
      this.paths = [];
      this.selectedPathId = null;
      this.collaborativeMode = false;
      this.collaborativeText = '';
      this.polishedResult = null;
      this.consistencyMode = false;
      this.consistencyReport = null;
      this.outlineMode = false;
      this.outlines = [];
      this.editingOutlineIdx = null;
    },
  };
}

export type { PipelineStatus, PipelineForm, PipelineResult, CheckpointItem };
