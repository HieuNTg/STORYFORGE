/**
 * branch-reader.ts — Alpine.js component for choose-your-own-adventure reader.
 * Register as Alpine.data('branchReader', ...) before Alpine initializes.
 */

interface BranchHistoryItem {
  id: string;
  preview: string;
  choiceLabel: string;
}

interface BranchTreeNode {
  id: string;
  text: string;
  choices?: string[];
}

interface BranchStartResponse {
  session_id: string;
  node: BranchTreeNode;
}

interface BranchChooseResponse {
  node: BranchTreeNode;
}

interface BranchBackResponse {
  node: BranchTreeNode;
}

interface BranchTreeResponse {
  nodes: Record<string, BranchTreeNode>;
  [key: string]: unknown;
}

interface BranchSessionStorage {
  sessionId: string;
  chapterIndex: number;
  storyTitle: string;
}

const BRANCH_STORAGE_KEY = 'sf_branch_session';

function saveBranchSession(sessionId: string, chapterIndex: number, storyTitle: string): void {
  try {
    localStorage.setItem(BRANCH_STORAGE_KEY, JSON.stringify({ sessionId, chapterIndex, storyTitle }));
  } catch { /* quota exceeded — ignore */ }
}

function loadBranchSession(): BranchSessionStorage | null {
  try {
    const raw = localStorage.getItem(BRANCH_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as BranchSessionStorage;
  } catch { return null; }
}

function clearBranchSession(): void {
  localStorage.removeItem(BRANCH_STORAGE_KEY);
}

interface BranchTreeLayout {
  layout: Record<string, { x: number; y: number }>;
  bounds: { min_x: number; max_x: number; max_y: number; width: number; height: number };
  stats: { total_nodes: number; max_depth: number; leaf_count: number };
}

interface MinimapData {
  nodes: Array<{ id: string; x: number; y: number; is_current: boolean; is_leaf: boolean }>;
  edges: Array<{ from: string; to: string }>;
  bounds: { min_x: number; max_x: number; max_y: number };
}

interface BookmarkItem {
  id: string;
  node_id: string;
  name: string;
  created_at: string;
}

interface AnalyticsData {
  total_visits: number;
  unique_paths: number;
  choice_distribution: Record<string, number>;
  popular_choices: Array<{ choice: string; count: number }>;
  depth_histogram: Record<number, number>;
}

interface BranchReaderComponent {
  sessionId: string | null;
  currentNode: BranchTreeNode | null;
  history: BranchHistoryItem[];
  loading: boolean;
  streaming: boolean;
  streamingText: string;
  error: string;
  treeData: BranchTreeResponse | null;
  treeLayout: BranchTreeLayout | null;
  minimapData: MinimapData | null;
  active: boolean;
  useStreaming: boolean;
  canUndo: boolean;
  canRedo: boolean;
  zoom: number;
  panX: number;
  panY: number;
  showMinimap: boolean;
  // New features
  bookmarks: BookmarkItem[];
  showBookmarks: boolean;
  analytics: AnalyticsData | null;
  showAnalytics: boolean;
  wsConnected: boolean;
  userCount: number;
  exportingEpub: boolean;
  _ws: WebSocket | null;
  // Methods
  startSession(text: string, context?: Record<string, unknown>): Promise<void>;
  restoreSession(sessionId: string): Promise<boolean>;
  choose(index: number): Promise<void>;
  chooseStream(index: number): Promise<void>;
  goBack(): Promise<void>;
  undo(): Promise<void>;
  redo(): Promise<void>;
  loadTree(): Promise<void>;
  loadTreeLayout(): Promise<void>;
  loadMinimap(): Promise<void>;
  zoomIn(): void;
  zoomOut(): void;
  resetZoom(): void;
  centerOnCurrent(): void;
  // New methods
  addBookmark(name: string): Promise<void>;
  removeBookmark(bookmarkId: string): Promise<void>;
  loadBookmarks(): Promise<void>;
  gotoBookmark(bookmarkId: string): Promise<void>;
  loadAnalytics(): Promise<void>;
  exportEpub(): Promise<void>;
  connectWebSocket(): void;
  disconnectWebSocket(): void;
  readonly depth: number;
  readonly isAtRoot: boolean;
  readonly nodeCount: number;
  close(): void;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('branchReader', (): BranchReaderComponent => {
    const self = {} as BranchReaderComponent;

    return Object.assign(self, {
      sessionId: null,
      currentNode: null,
      history: [],
      loading: false,
      streaming: false,
      streamingText: '',
      error: '',
      treeData: null,
      treeLayout: null,
      minimapData: null,
      active: false,
      useStreaming: false, // Prefer stable non-streaming choice; streaming endpoint may be unavailable in some deployments/tests.
      canUndo: false,
      canRedo: false,
      zoom: 1,
      panX: 0,
      panY: 0,
      showMinimap: true,
      // New features
      bookmarks: [],
      showBookmarks: false,
      analytics: null,
      showAnalytics: false,
      wsConnected: false,
      userCount: 1,
      exportingEpub: false,
      _ws: null,

      async startSession(this: BranchReaderComponent, text: string, context?: Record<string, unknown>): Promise<void> {
        if (!text || text.trim().length < 10) {
          this.error = 'Need at least 10 characters of story text.';
          return;
        }
        this.loading = true;
        this.error = '';
        this.history = [];
        this.treeData = null;
        try {
          const payload: Record<string, unknown> = { text: text.trim(), ...context };
          const res = await fetch('/api/branch/start', {
            method: 'POST',
            headers: mutationHeaders(),
            body: JSON.stringify(payload),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const d: BranchStartResponse = await res.json();
          this.sessionId = d.session_id;
          this.currentNode = d.node;
          this.active = true;
          document.dispatchEvent(new CustomEvent('branch:started', { detail: { sessionId: d.session_id } }));
        } catch (e) {
          this.error = (e as Error).message;
        } finally {
          this.loading = false;
        }
      },

      async restoreSession(this: BranchReaderComponent, sessionId: string): Promise<boolean> {
        this.loading = true;
        this.error = '';
        this.history = [];
        try {
          const res = await fetch(`/api/branch/${sessionId}/current`);
          if (!res.ok) {
            clearBranchSession();
            return false;
          }
          const d = await res.json();
          this.sessionId = sessionId;
          this.currentNode = d.node;
          this.active = true;
          return true;
        } catch {
          clearBranchSession();
          return false;
        } finally {
          this.loading = false;
        }
      },

      async choose(this: BranchReaderComponent, index: number): Promise<void> {
        // Use streaming if enabled
        if (this.useStreaming) {
          return this.chooseStream(index);
        }
        if (!this.sessionId || this.loading) return;
        const choiceLabel: string = this.currentNode?.choices?.[index] || `Choice ${index + 1}`;
        this.loading = true;
        this.error = '';
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/choose`, {
            method: 'POST',
            headers: mutationHeaders(),
            body: JSON.stringify({ choice_index: index }),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const d: BranchChooseResponse = await res.json();
          this.history.push({
            id: this.currentNode!.id,
            preview: this.currentNode!.text.slice(0, 60) + '...',
            choiceLabel,
          });
          this.currentNode = d.node;
          document.dispatchEvent(new CustomEvent('branch:navigated'));
        } catch (e) {
          this.error = (e as Error).message;
        } finally {
          this.loading = false;
        }
      },

      async chooseStream(this: BranchReaderComponent, index: number): Promise<void> {
        if (!this.sessionId || this.loading || this.streaming) return;
        const choiceLabel: string = this.currentNode?.choices?.[index] || `Choice ${index + 1}`;
        this.loading = true;
        this.streaming = true;
        this.streamingText = '';
        this.error = '';

        try {
          const res = await fetch(`/api/branch/${this.sessionId}/choose/stream`, {
            method: 'POST',
            headers: mutationHeaders(),
            body: JSON.stringify({ choice_index: index }),
          });

          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          if (!res.body) throw new Error('No response body');

          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (!line.startsWith('data: ')) continue;
              const data = line.slice(6);
              if (!data) continue;

              try {
                const event = JSON.parse(data);
                if (event.type === 'chunk') {
                  this.streamingText += event.text;
                } else if (event.type === 'complete') {
                  // Save history before updating current node
                  this.history.push({
                    id: this.currentNode!.id,
                    preview: this.currentNode!.text.slice(0, 60) + '...',
                    choiceLabel,
                  });
                  this.currentNode = event.node;
                  this.streamingText = '';
                  document.dispatchEvent(new CustomEvent('branch:navigated'));
                } else if (event.type === 'error') {
                  this.error = event.message;
                }
              } catch {
                // Ignore parse errors for incomplete JSON
              }
            }
          }
        } catch (e) {
          this.error = (e as Error).message;
        } finally {
          this.loading = false;
          this.streaming = false;
        }
      },

      async goBack(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId || this.loading) return;
        this.loading = true;
        this.error = '';
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/back`, {
            method: 'POST',
            headers: mutationHeaders(),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const d: BranchBackResponse = await res.json();
          this.currentNode = d.node;
          this.history.pop();
          document.dispatchEvent(new CustomEvent('branch:navigated'));
        } catch (e) {
          this.error = (e as Error).message;
        } finally {
          this.loading = false;
        }
      },

      async undo(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId || this.loading || !this.canUndo) return;
        this.loading = true;
        this.error = '';
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/undo`, {
            method: 'POST',
            headers: mutationHeaders(),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const d = await res.json();
          this.currentNode = d.node;
          this.canUndo = d.can_undo;
          this.canRedo = d.can_redo;
          document.dispatchEvent(new CustomEvent('branch:navigated'));
        } catch (e) {
          this.error = (e as Error).message;
        } finally {
          this.loading = false;
        }
      },

      async redo(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId || this.loading || !this.canRedo) return;
        this.loading = true;
        this.error = '';
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/redo`, {
            method: 'POST',
            headers: mutationHeaders(),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const d = await res.json();
          this.currentNode = d.node;
          this.canUndo = d.can_undo;
          this.canRedo = d.can_redo;
          document.dispatchEvent(new CustomEvent('branch:navigated'));
        } catch (e) {
          this.error = (e as Error).message;
        } finally {
          this.loading = false;
        }
      },

      async loadTree(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId) return;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/tree`);
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          this.treeData = await res.json();
        } catch (e) {
          this.error = (e as Error).message;
        }
      },

      async loadTreeLayout(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId) return;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/tree/layout`);
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          this.treeLayout = await res.json();
        } catch (e) {
          this.error = (e as Error).message;
        }
      },

      async loadMinimap(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId) return;
        this.minimapData = null;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/tree/minimap`);
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const data = await res.json();
          const hasShape = Array.isArray(data?.nodes) && Array.isArray(data?.edges) && data?.bounds;
          this.minimapData = hasShape ? data : null;
        } catch {
          // Minimap is optional chrome. Do not break the branch reader if the
          // endpoint is missing or returns an older tree shape.
          this.minimapData = null;
        }
      },

      zoomIn(this: BranchReaderComponent): void {
        this.zoom = Math.min(this.zoom * 1.2, 3);
      },

      zoomOut(this: BranchReaderComponent): void {
        this.zoom = Math.max(this.zoom / 1.2, 0.3);
      },

      resetZoom(this: BranchReaderComponent): void {
        this.zoom = 1;
        this.panX = 0;
        this.panY = 0;
      },

      centerOnCurrent(this: BranchReaderComponent): void {
        if (!this.treeLayout || !this.currentNode) return;
        const pos = this.treeLayout.layout[this.currentNode.id];
        if (pos) {
          // Center the view on the current node
          this.panX = -pos.x * 100; // Assuming 100px per unit
          this.panY = -pos.y * 100;
        }
      },

      get depth(): number {
        return this.history.length;
      },

      get isAtRoot(): boolean {
        return this.history.length === 0;
      },

      get nodeCount(): number {
        return this.treeData ? Object.keys(this.treeData.nodes || {}).length : 0;
      },

      async addBookmark(this: BranchReaderComponent, name: string): Promise<void> {
        if (!this.sessionId || !this.currentNode) return;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/bookmarks`, {
            method: 'POST',
            headers: mutationHeaders(),
            body: JSON.stringify({ node_id: this.currentNode.id, name }),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          await this.loadBookmarks();
        } catch (e) {
          this.error = (e as Error).message;
        }
      },

      async removeBookmark(this: BranchReaderComponent, bookmarkId: string): Promise<void> {
        if (!this.sessionId) return;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/bookmarks/${bookmarkId}`, {
            method: 'DELETE',
            headers: mutationHeaders(),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          this.bookmarks = this.bookmarks.filter(b => b.id !== bookmarkId);
        } catch (e) {
          this.error = (e as Error).message;
        }
      },

      async loadBookmarks(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId) return;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/bookmarks`);
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const data = await res.json();
          this.bookmarks = data.bookmarks || [];
        } catch (e) {
          this.error = (e as Error).message;
        }
      },

      async gotoBookmark(this: BranchReaderComponent, bookmarkId: string): Promise<void> {
        if (!this.sessionId) return;
        this.loading = true;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/bookmarks/${bookmarkId}/goto`, {
            method: 'POST',
            headers: mutationHeaders(),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const data = await res.json();
          this.currentNode = data.node;
          this.history = [];
          document.dispatchEvent(new CustomEvent('branch:navigated'));
        } catch (e) {
          this.error = (e as Error).message;
        } finally {
          this.loading = false;
        }
      },

      async loadAnalytics(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId) return;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/analytics`);
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          this.analytics = await res.json();
        } catch (e) {
          this.error = (e as Error).message;
        }
      },

      async exportEpub(this: BranchReaderComponent): Promise<void> {
        if (!this.sessionId) return;
        this.exportingEpub = true;
        try {
          const res = await fetch(`/api/branch/${this.sessionId}/export/epub`, {
            method: 'POST',
            headers: mutationHeaders(),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const blob = await res.blob();
          const url = URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `branch-story-${this.sessionId.slice(0, 8)}.epub`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          URL.revokeObjectURL(url);
        } catch (e) {
          this.error = (e as Error).message;
        } finally {
          this.exportingEpub = false;
        }
      },

      connectWebSocket(this: BranchReaderComponent): void {
        if (!this.sessionId || this._ws) return;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const ws = new WebSocket(`${protocol}//${window.location.host}/api/ws/branch/${this.sessionId}`);

        ws.onopen = () => {
          this.wsConnected = true;
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'sync' || data.type === 'navigation') {
              this.currentNode = data.node;
              this.userCount = data.user_count || 1;
              if (data.type === 'navigation') {
                document.dispatchEvent(new CustomEvent('branch:navigated'));
              }
            } else if (data.type === 'user_joined' || data.type === 'user_left') {
              this.userCount = data.user_count || 1;
            }
          } catch { /* ignore */ }
        };

        ws.onclose = () => {
          this.wsConnected = false;
          this._ws = null;
        };

        ws.onerror = () => {
          this.wsConnected = false;
        };

        this._ws = ws;
      },

      disconnectWebSocket(this: BranchReaderComponent): void {
        if (this._ws) {
          this._ws.close();
          this._ws = null;
          this.wsConnected = false;
        }
      },

      close(this: BranchReaderComponent): void {
        this.disconnectWebSocket();
        this.active = false;
        clearBranchSession();
      },
    } satisfies BranchReaderComponent);
  });
});
