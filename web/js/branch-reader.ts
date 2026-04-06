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

interface BranchReaderData {
  sessionId: string | null;
  currentNode: BranchTreeNode | null;
  history: BranchHistoryItem[];
  loading: boolean;
  error: string;
  treeData: BranchTreeResponse | null;
  active: boolean;
  startSession(text: string): Promise<void>;
  restoreSession(sessionId: string): Promise<boolean>;
  choose(index: number): Promise<void>;
  goBack(): Promise<void>;
  loadTree(): Promise<void>;
  readonly depth: number;
  readonly isAtRoot: boolean;
  readonly nodeCount: number;
  close(): void;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('branchReader', () => {
    const data: BranchReaderData = {
      sessionId: null,
      currentNode: null,
      history: [],       // breadcrumb: [{id, text_preview, choiceLabel}]
      loading: false,
      error: '',
      treeData: null,
      active: false,     // panel visibility

      // ── init ────────────────────────────────────────────────────────

      async startSession(text: string): Promise<void> {
        if (!text || text.trim().length < 10) {
          data.error = 'Need at least 10 characters of story text.';
          return;
        }
        data.loading = true;
        data.error = '';
        data.history = [];
        data.treeData = null;
        try {
          const res = await fetch('/api/branch/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text.trim() }),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const d: BranchStartResponse = await res.json();
          data.sessionId = d.session_id;
          data.currentNode = d.node;
          data.active = true;
          document.dispatchEvent(new CustomEvent('branch:started', { detail: { sessionId: d.session_id } }));
        } catch (e) {
          data.error = (e as Error).message;
        } finally {
          data.loading = false;
        }
      },

      async restoreSession(sessionId: string): Promise<boolean> {
        data.loading = true;
        data.error = '';
        data.history = [];
        try {
          const res = await fetch(`/api/branch/${sessionId}/current`);
          if (!res.ok) {
            clearBranchSession();
            return false;
          }
          const d = await res.json();
          data.sessionId = sessionId;
          data.currentNode = d.node;
          data.active = true;
          return true;
        } catch {
          clearBranchSession();
          return false;
        } finally {
          data.loading = false;
        }
      },

      // ── navigation ──────────────────────────────────────────────────

      async choose(index: number): Promise<void> {
        if (!data.sessionId || data.loading) return;
        const choiceLabel: string = data.currentNode?.choices?.[index] || `Choice ${index + 1}`;
        data.loading = true;
        data.error = '';
        try {
          const res = await fetch(`/api/branch/${data.sessionId}/choose`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ choice_index: index }),
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const d: BranchChooseResponse = await res.json();
          data.history.push({
            id: data.currentNode!.id,
            preview: data.currentNode!.text.slice(0, 60) + '...',
            choiceLabel,
          });
          data.currentNode = d.node;
          document.dispatchEvent(new CustomEvent('branch:navigated'));
        } catch (e) {
          data.error = (e as Error).message;
        } finally {
          data.loading = false;
        }
      },

      async goBack(): Promise<void> {
        if (!data.sessionId || data.loading) return;
        data.loading = true;
        data.error = '';
        try {
          const res = await fetch(`/api/branch/${data.sessionId}/back`, {
            method: 'POST',
          });
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          const d: BranchBackResponse = await res.json();
          data.currentNode = d.node;
          data.history.pop();
          document.dispatchEvent(new CustomEvent('branch:navigated'));
        } catch (e) {
          data.error = (e as Error).message;
        } finally {
          data.loading = false;
        }
      },

      async loadTree(): Promise<void> {
        if (!data.sessionId) return;
        try {
          const res = await fetch(`/api/branch/${data.sessionId}/tree`);
          if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
          data.treeData = await res.json();
        } catch (e) {
          data.error = (e as Error).message;
        }
      },

      // ── helpers ─────────────────────────────────────────────────────

      get depth(): number {
        return data.history.length;
      },

      get isAtRoot(): boolean {
        return data.history.length === 0;
      },

      get nodeCount(): number {
        return data.treeData ? Object.keys(data.treeData.nodes || {}).length : 0;
      },

      close(): void {
        data.active = false;
        clearBranchSession();
      },
    };
    return data;
  });
});
