/**
 * StoryForge — Alpine.js app stores and SPA routing.
 */

/* ── Navigation items ── */
const NAV_ITEMS = [
  { id: 'pipeline',  label: 'Create Story',  icon: 'pencil-square', group: 'main' },
  { id: 'reader',    label: 'Reader',        icon: 'book-open',     group: 'main' },
  { id: 'export',    label: 'Export',        icon: 'arrow-down-tray', group: 'main' },
  { id: 'analytics', label: 'Analytics',    icon: 'chart-bar',     group: 'main' },
  { id: 'branching', label: 'Branching',    icon: 'arrows-pointing-out', group: 'main' },
  { id: 'settings',  label: 'Settings',     icon: 'cog-6-tooth',   group: 'bottom' },
  { id: 'guide',     label: 'Guide',        icon: 'question-mark-circle', group: 'bottom' },
];

/* ── Global app store ── */
document.addEventListener('alpine:init', () => {

  Alpine.store('app', {
    page: 'pipeline',
    sidebarOpen: window.innerWidth > 768,
    loading: false,
    sessionId: null,
    pipelineResult: null,
    storageWarning: '',

    navItems: NAV_ITEMS,

    navigate(page) {
      this.page = page;
      if (window.innerWidth <= 768) this.sidebarOpen = false;
      window.location.hash = page;
    },

    toggleSidebar() {
      this.sidebarOpen = !this.sidebarOpen;
    },

    /** Save pipeline result to sessionStorage with error handling */
    savePipelineResult(data) {
      this.pipelineResult = data;
      this.storageWarning = '';
      try {
        // Strip transient fields before storage
        const toStore = { ...data };
        delete toStore.livePreview;
        const json = JSON.stringify(toStore);

        // Warn if approaching typical 5MB limit
        if (json.length > 4 * 1024 * 1024) {
          console.warn('Pipeline result large (' + Math.round(json.length / 1024) + 'KB)');
        }
        sessionStorage.setItem('sf_result', json);
      } catch (e) {
        console.error('sessionStorage save failed:', e.message);
        this.storageWarning = 'Result too large to cache. It will be lost on page refresh.';
      }
    },

    init() {
      // Restore page from hash
      const hash = window.location.hash.slice(1);
      if (hash && NAV_ITEMS.some(n => n.id === hash)) {
        this.page = hash;
      }
      window.addEventListener('hashchange', () => {
        const h = window.location.hash.slice(1);
        if (h && NAV_ITEMS.some(n => n.id === h)) {
          this.page = h;
        }
      });
      // Restore pipeline result from sessionStorage
      try {
        const saved = sessionStorage.getItem('sf_result');
        if (saved) {
          const parsed = JSON.parse(saved);
          if (parsed && typeof parsed === 'object') {
            this.pipelineResult = parsed;
            Alpine.store('pipeline').result = parsed;
            Alpine.store('pipeline').status = 'done';
            Alpine.store('pipeline').progress = 4;
          }
        }
      } catch (e) {
        console.warn('Failed to restore pipeline result:', e.message);
        sessionStorage.removeItem('sf_result');
      }
    },
  });

  /* ── Pipeline store ── */
  Alpine.store('pipeline', {
    status: 'idle',  // idle | running | done | error | interrupted
    currentLog: '',
    logs: [],
    livePreview: '',
    progress: 0,     // 0-4 (layer number)
    result: null,
    error: null,
    checkpoints: [],

    // Form defaults
    form: {
      title: '', genre: 'Tiên Hiệp', style: 'Miêu tả chi tiết',
      idea: '', num_chapters: 5, num_characters: 5, word_count: 2000,
      num_sim_rounds: 3, drama_level: 'cao', shots_per_chapter: 8,
      enable_agents: true, enable_scoring: true, enable_media: false,
    },

    genres: [], styles: [], dramaLevels: [],
    templates: {},

    async loadChoices() {
      try {
        const data = await API.get('/pipeline/genres');
        this.genres = data.genres || [];
        this.styles = data.styles || [];
        this.dramaLevels = data.drama_levels || [];
      } catch (e) { console.error('Load choices failed:', e); }
    },

    async loadTemplates() {
      try {
        this.templates = await API.get('/pipeline/templates');
      } catch (e) { console.error('Load templates failed:', e); }
    },

    async run() {
      // Client-side validation
      const idea = (this.form.idea || '').trim();
      if (!idea || idea.length < 10) {
        this.error = 'Please enter a story idea (at least 10 characters).';
        this.status = 'error';
        return;
      }

      this.status = 'running';
      this.logs = [];
      this.livePreview = '';
      this.progress = 0;
      this.result = null;
      this.error = null;

      try {
        for await (const event of API.stream('/pipeline/run', this.form)) {
          if (event.type === 'session') {
            Alpine.store('app').sessionId = event.session_id;
          } else if (event.type === 'log') {
            this.currentLog = event.data;
            this.logs.push(event.data);
            this.progress = this._detectLayer(event.data);
          } else if (event.type === 'stream') {
            this.livePreview = event.data;
          } else if (event.type === 'done') {
            this.result = event.data;
            Alpine.store('app').savePipelineResult(event.data);
            Alpine.store('app').sessionId = event.data.session_id;
            this.status = 'done';
            this.progress = 4;
          } else if (event.type === 'error') {
            this.error = event.data;
            this.status = 'error';
          } else if (event.type === 'interrupted') {
            this.error = 'Connection lost. You can resume from the last checkpoint.';
            this.status = 'interrupted';
          }
        }
        if (this.status === 'running') this.status = 'done';
      } catch (e) {
        this.error = e.message;
        this.status = 'error';
      }
    },

    async loadCheckpoints() {
      try {
        const data = await API.get('/pipeline/checkpoints');
        this.checkpoints = data.checkpoints || [];
      } catch (e) {
        console.error('Load checkpoints failed:', e);
        this.checkpoints = [];
      }
    },

    async resumeFromCheckpoint(path) {
      this.status = 'running';
      this.logs = [];
      this.livePreview = '';
      this.error = null;

      try {
        for await (const event of API.stream('/pipeline/resume', { checkpoint: path })) {
          if (event.type === 'session') {
            Alpine.store('app').sessionId = event.session_id;
          } else if (event.type === 'log') {
            this.currentLog = event.data;
            this.logs.push(event.data);
            this.progress = this._detectLayer(event.data);
          } else if (event.type === 'stream') {
            this.livePreview = event.data;
          } else if (event.type === 'done') {
            this.result = event.data;
            Alpine.store('app').savePipelineResult(event.data);
            Alpine.store('app').sessionId = event.data.session_id;
            this.status = 'done';
            this.progress = 4;
          } else if (event.type === 'error') {
            this.error = event.data;
            this.status = 'error';
          } else if (event.type === 'interrupted') {
            this.error = 'Connection lost during resume.';
            this.status = 'interrupted';
          }
        }
        if (this.status === 'running') this.status = 'done';
      } catch (e) {
        this.error = e.message;
        this.status = 'error';
      }
    },

    _detectLayer(msg) {
      const up = msg.toUpperCase();
      if (up.includes('MEDIA') || up.includes('IMAGE') || up.includes('AUDIO')) return 4;
      if (up.includes('LAYER 3') || up.includes('STORYBOARD') || up.includes('VIDEO')) return 3;
      if (up.includes('LAYER 2') || up.includes('MO PHONG') || up.includes('ENHANCE')) return 2;
      if (up.includes('LAYER 1') || up.includes('TAO TRUYEN') || up.includes('CHUONG')) return 1;
      return this.progress || 0;
    },

    reset() {
      this.status = 'idle';
      this.logs = [];
      this.livePreview = '';
      this.progress = 0;
      this.result = null;
      this.error = null;
      this.checkpoints = [];
    },
  });

  /* ── Settings store ── */
  Alpine.store('settings', {
    config: null,
    saving: false,
    message: '',

    async load() {
      try {
        this.config = await API.get('/config');
      } catch (e) { console.error('Load config failed:', e); }
    },

    async save(formData) {
      this.saving = true;
      this.message = '';
      try {
        await API.put('/config', formData);
        this.message = 'Settings saved!';
        await this.load();
      } catch (e) {
        this.message = 'Error: ' + e.message;
      }
      this.saving = false;
    },

    async testConnection() {
      try {
        const res = await API.post('/config/test-connection');
        return res.ok ? 'OK: ' + res.message : 'Error: ' + res.message;
      } catch (e) { return 'Error: ' + e.message; }
    },
  });

  // Init: load choices and config
  Alpine.store('pipeline').loadChoices();
  Alpine.store('pipeline').loadTemplates();
  Alpine.store('settings').load();
});
