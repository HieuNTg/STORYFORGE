/**
 * branch-reader.js — Alpine.js component for choose-your-own-adventure reader.
 * Register as Alpine.data('branchReader', ...) before Alpine initializes.
 */
document.addEventListener('alpine:init', () => {
  Alpine.data('branchReader', () => ({
    sessionId: null,
    currentNode: null,
    history: [],       // breadcrumb: [{id, text_preview, choiceLabel}]
    loading: false,
    error: '',
    treeData: null,
    active: false,     // panel visibility

    // ── init ──────────────────────────────────────────────────────────────

    async startSession(text) {
      if (!text || text.trim().length < 10) {
        this.error = 'Need at least 10 characters of story text.';
        return;
      }
      this.loading = true;
      this.error = '';
      this.history = [];
      this.treeData = null;
      try {
        const res = await fetch('/api/branch/start', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: text.trim() }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const data = await res.json();
        this.sessionId = data.session_id;
        this.currentNode = data.node;
        this.active = true;
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    // ── navigation ────────────────────────────────────────────────────────

    async choose(index) {
      if (!this.sessionId || this.loading) return;
      const choiceLabel = this.currentNode?.choices?.[index] || `Choice ${index + 1}`;
      this.loading = true;
      this.error = '';
      try {
        const res = await fetch(`/api/branch/${this.sessionId}/choose`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ choice_index: index }),
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const data = await res.json();
        this.history.push({
          id: this.currentNode.id,
          preview: this.currentNode.text.slice(0, 60) + '...',
          choiceLabel,
        });
        this.currentNode = data.node;
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    async goBack() {
      if (!this.sessionId || this.loading) return;
      this.loading = true;
      this.error = '';
      try {
        const res = await fetch(`/api/branch/${this.sessionId}/back`, {
          method: 'POST',
        });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const data = await res.json();
        this.currentNode = data.node;
        this.history.pop();
      } catch (e) {
        this.error = e.message;
      } finally {
        this.loading = false;
      }
    },

    async loadTree() {
      if (!this.sessionId) return;
      try {
        const res = await fetch(`/api/branch/${this.sessionId}/tree`);
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        this.treeData = await res.json();
      } catch (e) {
        this.error = e.message;
      }
    },

    // ── helpers ───────────────────────────────────────────────────────────

    get depth() {
      return this.history.length;
    },

    get isAtRoot() {
      return this.history.length === 0;
    },

    get nodeCount() {
      return this.treeData ? Object.keys(this.treeData.nodes || {}).length : 0;
    },

    close() {
      this.active = false;
    },
  }));
});
