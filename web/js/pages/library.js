"use strict";
/**
 * Library page — browse saved stories and read inline.
 * Combines library (story list) + reader (chapter view) into one page.
 */
function libraryPage() {
    return {
        // Library state
        stories: [],
        loading: false,
        error: '',
        loadingStory: null,
        confirmDelete: null,
        searchQuery: '',
        qualityFilter: 'all',
        qualitySummaries: {},
        generatingImages: null,
        generatingChapterImage: null,
        rebuildingProfile: null,
        uploadingReference: null,
        imageStatus: '',
        // Reader state
        selectedStory: null,
        chapter: 0,
        fontSize: 18,
        characterProfiles: [],
        showCharacterPanel: false,
        qualityScores: null,
        showQualityPanel: false,
        readerUsage: null,
        latestContinuation: null,
        jumpDismissed: false,
        // Computed: current view mode
        get isReading() {
            return this.selectedStory !== null;
        },
        get story() {
            if (!this.selectedStory)
                return null;
            return this.selectedStory.enhanced || this.selectedStory.draft || null;
        },
        get chapters() {
            if (!this.story)
                return [];
            return this.story.chapters || [];
        },
        get currentChapter() {
            return this.chapters[this.chapter] || null;
        },
        get filteredStories() {
            const q = this.searchQuery.toLowerCase();
            return this.stories.filter((s) => {
                if (q) {
                    const matchesSearch = (s.title || s.path).toLowerCase().includes(q) ||
                        (s.genre || '').toLowerCase().includes(q);
                    if (!matchesSearch)
                        return false;
                }
                if (this.qualityFilter === 'all')
                    return true;
                const summary = this.qualitySummaries[s.path];
                if (this.qualityFilter === 'scored')
                    return !!summary;
                return !summary; // 'unscored'
            });
        },
        init() {
            this.loadStories().then(() => this.loadQualitySummaries());
        },
        async loadStories() {
            this.loading = true;
            this.error = '';
            try {
                const data = await API.get('/pipeline/checkpoints');
                this.stories = data.checkpoints || [];
            }
            catch (e) {
                this.error = 'Failed to load stories: ' + e.message;
                this.stories = [];
            }
            this.loading = false;
        },
        async loadQualitySummaries() {
            try {
                const data = await API.get('/quality');
                this.qualitySummaries = data.summaries || {};
            }
            catch {
                // Silent — summaries are an enhancement; library still works without them.
                this.qualitySummaries = {};
            }
        },
        qualityForStory(path) {
            return this.qualitySummaries[path] || null;
        },
        // Continuation pill: only show event if it landed within the last 7 days.
        recentContinuationFor(story) {
            const ev = story.latest_continuation;
            if (!ev || !ev.ts)
                return null;
            const t = Date.parse(ev.ts);
            if (!Number.isFinite(t))
                return null;
            const ageDays = (Date.now() - t) / 86400000;
            return ageDays >= 0 && ageDays <= 7 ? ev : null;
        },
        // Compact "X giờ trước" / "X ngày trước" — small enough to inline.
        relativeTimeVi(iso) {
            const t = Date.parse(iso);
            if (!Number.isFinite(t))
                return '';
            const diff = Math.max(0, Date.now() - t);
            const minutes = Math.floor(diff / 60000);
            if (minutes < 1)
                return 'vừa xong';
            if (minutes < 60)
                return `${minutes} phút trước`;
            const hours = Math.floor(minutes / 60);
            if (hours < 24)
                return `${hours} giờ trước`;
            const days = Math.floor(hours / 24);
            return `${days} ngày trước`;
        },
        // Reader jump-to-new-chapter: returns 1-indexed chapter number of first new chapter.
        get firstNewChapter() {
            const ev = this.latestContinuation;
            if (!ev)
                return null;
            const ageDays = (Date.now() - Date.parse(ev.ts)) / 86400000;
            if (!Number.isFinite(ageDays) || ageDays > 7)
                return null;
            return ev.previous_chapter_count + 1;
        },
        get showJumpToNew() {
            if (this.jumpDismissed || !this.firstNewChapter)
                return false;
            // Hide once the user has already navigated to/past the first new chapter.
            return this.chapter + 1 < this.firstNewChapter;
        },
        jumpToNewChapter() {
            const target = this.firstNewChapter;
            if (target == null)
                return;
            const idx = Math.min(target - 1, Math.max(0, this.chapters.length - 1));
            this.chapter = idx;
            this.jumpDismissed = true;
        },
        overallPillClass(value) {
            if (value >= 4)
                return 'bg-emerald-100 text-emerald-700 border-emerald-200';
            if (value >= 3)
                return 'bg-amber-100 text-amber-700 border-amber-200';
            return 'bg-rose-100 text-rose-700 border-rose-200';
        },
        // ── Usage cost pill (Piece L) ──────────────────────────────────────────
        usageForStory(story) {
            const u = story.usage_summary;
            if (!u || u.call_count <= 0)
                return null;
            return u;
        },
        formatTokens(n) {
            if (n >= 1000000)
                return `${(n / 1000000).toFixed(1)}M`;
            if (n >= 1000)
                return `${Math.round(n / 1000)}k`;
            return String(n);
        },
        formatUsageLabel(u) {
            const tokens = `${this.formatTokens(u.total_tokens)} tokens`;
            const calls = `${u.call_count} calls`;
            // Unknown-model sidecars yield cost=0 with tokens>0 — show tokens only.
            if (u.total_cost_usd <= 0)
                return `${tokens} · ${calls}`;
            const dollars = u.total_cost_usd >= 1
                ? `$${u.total_cost_usd.toFixed(2)}`
                : `$${u.total_cost_usd.toFixed(3)}`;
            return `${dollars} · ${tokens} · ${calls}`;
        },
        usagePillClass(u) {
            if (u.total_cost_usd <= 0)
                return 'bg-slate-100 text-slate-600 border-slate-200';
            if (u.total_cost_usd < 0.5)
                return 'bg-emerald-100 text-emerald-700 border-emerald-200';
            if (u.total_cost_usd < 2)
                return 'bg-amber-100 text-amber-700 border-amber-200';
            return 'bg-rose-100 text-rose-700 border-rose-200';
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
                // Set selected story for inline reading
                this.selectedStory = data;
                this.chapter = 0;
                this.characterProfiles = [];
                this.qualityScores = null;
                this.jumpDismissed = false;
                this.latestContinuation =
                    this.stories.find((s) => s.path === filename)?.latest_continuation || null;
                // Also update global stores for compatibility
                Alpine.store('pipeline').result = data;
                Alpine.store('pipeline').status = 'done';
                Alpine.store('pipeline').progress = 4;
                Alpine.store('app').pipelineResult = data;
                // Fire-and-forget: don't block reader render on profiles or quality
                this.loadCharacterProfiles(filename);
                this.loadQuality(filename);
                this.loadUsage(filename);
            }
            catch (e) {
                this.error = 'Failed to load story: ' + e.message;
            }
            this.loadingStory = null;
        },
        async loadCharacterProfiles(filename) {
            try {
                const data = await API.get('/images/' + encodeURIComponent(filename) + '/profiles');
                this.characterProfiles = data.profiles || [];
            }
            catch {
                this.characterProfiles = [];
            }
        },
        async loadQuality(filename) {
            try {
                const data = await API.get('/quality/' + encodeURIComponent(filename));
                this.qualityScores = data;
            }
            catch {
                // Older checkpoints / 404 → silently leave panel hidden.
                this.qualityScores = null;
            }
        },
        async loadUsage(filename) {
            try {
                const data = await API.get('/usage/story/' + encodeURIComponent(filename));
                const t = data?.totals;
                this.readerUsage = t && t.call_count > 0 ? t : null;
            }
            catch {
                this.readerUsage = null;
            }
        },
        chapterScore(chapterNumber) {
            const list = this.qualityScores?.chapters || [];
            return list.find((c) => c.chapter_number === chapterNumber) || null;
        },
        scoreColor(value) {
            // 1-5 scale: ≥3.75 green, 2.5-3.75 amber, <2.5 red.
            if (value >= 3.75)
                return 'bg-emerald-100 text-emerald-700 border-emerald-200';
            if (value >= 2.5)
                return 'bg-amber-100 text-amber-700 border-amber-200';
            return 'bg-rose-100 text-rose-700 border-rose-200';
        },
        backToList() {
            this.selectedStory = null;
            this.chapter = 0;
            this.characterProfiles = [];
            this.showCharacterPanel = false;
            this.qualityScores = null;
            this.showQualityPanel = false;
            this.readerUsage = null;
            this.latestContinuation = null;
            this.jumpDismissed = false;
        },
        async deleteStory(filename) {
            this.error = '';
            try {
                const data = await API.del('/pipeline/checkpoints/' + encodeURIComponent(filename));
                if (data.error) {
                    this.error = data.error;
                }
                else {
                    this.stories = this.stories.filter((s) => s.path !== filename);
                }
            }
            catch (e) {
                this.error = 'Failed to delete: ' + e.message;
            }
            this.confirmDelete = null;
        },
        continueStory(story) {
            const s = story || (this.selectedStory ? {
                path: this.selectedStory.filename || '',
                title: this.story?.title || '',
                chapter_count: this.chapters.length,
                genre: this.story?.genre || '',
            } : null);
            if (!s)
                return;
            Alpine.store('pipeline').startContinuation({
                checkpoint: s.path,
                title: s.title || s.path,
                chapterCount: s.chapter_count || 0,
                genre: s.genre || '',
            });
            Alpine.store('app').navigate('pipeline');
        },
        // Piece N: resume an interrupted story by pre-filling the continuation form
        // with the missing-chapter delta, then handing off to the pipeline page.
        resumeStory(story) {
            if (!story?.path)
                return;
            const target = story.target_chapters || 0;
            const written = story.chapter_count || 0;
            const delta = Math.max(1, target - written);
            const pipelineStore = Alpine.store('pipeline');
            // Pre-fill the form so the pipeline page lands ready-to-run.
            if (pipelineStore.form) {
                pipelineStore.form.num_chapters = delta;
            }
            pipelineStore.startContinuation({
                checkpoint: story.path,
                title: story.title || story.path,
                chapterCount: written,
                genre: story.genre || '',
            });
            Alpine.store('app').navigate('pipeline');
        },
        // Piece N: surface "interrupted" pill when the server-derived flag is set.
        // We trust the server fields; the helper just guards against undefined.
        interruptedInfo(story) {
            if (!story.interrupted || !story.resume_from_chapter)
                return null;
            return {
                resumeFrom: story.resume_from_chapter,
                target: story.target_chapters || 0,
            };
        },
        async generateImages(story) {
            if (!story?.path)
                return;
            this.generatingImages = story.path;
            this.imageStatus = '';
            this.error = '';
            try {
                const data = await API.post('/images/' + encodeURIComponent(story.path) + '/generate', {});
                this.imageStatus = data.message || `Đã tạo ${data.count} ảnh`;
                // If we are currently reading this story, splice the new images onto loaded chapters.
                if (this.selectedStory && this.selectedStory.filename === story.path && data.chapter_images) {
                    const map = data.chapter_images;
                    const target = (this.selectedStory.enhanced || this.selectedStory.draft);
                    target?.chapters?.forEach((ch) => {
                        const n = ch.chapter_number;
                        if (n != null && map[String(n)]) {
                            ch.images = map[String(n)];
                        }
                    });
                }
            }
            catch (e) {
                this.error = 'Tạo ảnh thất bại: ' + e.message;
            }
            this.generatingImages = null;
            setTimeout(() => { this.imageStatus = ''; }, 5000);
        },
        async generateChapterImage(chapterNumber) {
            // Reader-side regen: only the currently-loaded story's single chapter.
            const filename = this.selectedStory?.filename;
            if (!filename || chapterNumber == null)
                return;
            this.generatingChapterImage = chapterNumber;
            this.imageStatus = '';
            this.error = '';
            try {
                const data = await API.post('/images/' + encodeURIComponent(filename) + '/generate', { chapter: chapterNumber });
                this.imageStatus = data.message || `Đã tạo ${data.count} ảnh cho chương ${chapterNumber}`;
                const map = data.chapter_images || {};
                const target = (this.selectedStory?.enhanced || this.selectedStory?.draft);
                const ch = target?.chapters?.find((c) => c.chapter_number === chapterNumber);
                if (ch && map[String(chapterNumber)]) {
                    ch.images = map[String(chapterNumber)];
                }
            }
            catch (e) {
                this.error = 'Tạo ảnh chương thất bại: ' + e.message;
            }
            this.generatingChapterImage = null;
            setTimeout(() => { this.imageStatus = ''; }, 5000);
        },
        async rebuildCharacterProfile(name) {
            const filename = this.selectedStory?.filename;
            if (!filename || !name || this.rebuildingProfile)
                return;
            this.rebuildingProfile = name;
            this.error = '';
            try {
                const data = await API.post('/images/' + encodeURIComponent(filename) +
                    '/profiles/' + encodeURIComponent(name) + '/rebuild', {});
                const idx = this.characterProfiles.findIndex((p) => p.name === data.name);
                const next = {
                    name: data.name,
                    frozen_prompt: data.frozen_prompt,
                    prompt_version: data.prompt_version,
                    has_reference_image: data.has_reference_image,
                    reference_url: data.reference_url,
                };
                if (idx >= 0)
                    this.characterProfiles.splice(idx, 1, next);
                else
                    this.characterProfiles.push(next);
            }
            catch (e) {
                this.error = 'Tạo lại hồ sơ thất bại: ' + e.message;
            }
            this.rebuildingProfile = null;
        },
        async uploadReference(name, file) {
            const filename = this.selectedStory?.filename;
            if (!filename || !name || !file || this.uploadingReference)
                return;
            this.uploadingReference = name;
            this.error = '';
            try {
                const form = new FormData();
                form.append('file', file);
                const csrf = document.cookie.match(/(?:^|; )csrf_token=([^;]*)/);
                const headers = {};
                if (csrf)
                    headers['X-CSRF-Token'] = decodeURIComponent(csrf[1]);
                const res = await fetch('/api/images/' + encodeURIComponent(filename) +
                    '/profiles/' + encodeURIComponent(name) + '/reference', { method: 'POST', headers, body: form });
                if (!res.ok) {
                    let detail = `Upload: ${res.status}`;
                    try {
                        const body = await res.json();
                        if (body.detail)
                            detail = body.detail;
                    }
                    catch { /* ignore */ }
                    throw new Error(detail);
                }
                const data = await res.json();
                const idx = this.characterProfiles.findIndex((p) => p.name === data.name);
                const next = {
                    name: data.name,
                    frozen_prompt: data.frozen_prompt,
                    prompt_version: data.prompt_version,
                    has_reference_image: data.has_reference_image,
                    reference_url: data.reference_url,
                };
                if (idx >= 0)
                    this.characterProfiles.splice(idx, 1, next);
                else
                    this.characterProfiles.push(next);
            }
            catch (e) {
                this.error = 'Tải ảnh tham chiếu thất bại: ' + e.message;
            }
            this.uploadingReference = null;
        },
        layerLabel(layer) {
            const labels = { 1: 'Draft', 2: 'Enhanced', 3: 'Complete' };
            return labels[layer] || 'Draft';
        },
        layerColor(layer) {
            if (layer >= 3)
                return 'bg-green-100 text-green-700';
            if (layer === 2)
                return 'bg-blue-100 text-blue-700';
            return 'bg-amber-100 text-amber-700';
        },
        // Reader navigation
        prev() { if (this.chapter > 0)
            this.chapter--; },
        next() { if (this.chapter < this.chapters.length - 1)
            this.chapter++; },
    };
}
