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

interface BranchReaderComponent {
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
  Alpine.data('branchReader', (): BranchReaderComponent => {
    const self = {} as BranchReaderComponent;

    return Object.assign(self, {
      sessionId: null,
      currentNode: null,
      history: [],
      loading: false,
      error: '',
      treeData: null,
      active: false,

      async startSession(this: BranchReaderComponent, text: string): Promise<void> {
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
            headers: mutationHeaders(),
            body: JSON.stringify({ text: text.trim() }),
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

      get depth(): number {
        return this.history.length;
      },

      get isAtRoot(): boolean {
        return this.history.length === 0;
      },

      get nodeCount(): number {
        return this.treeData ? Object.keys(this.treeData.nodes || {}).length : 0;
      },

      close(this: BranchReaderComponent): void {
        this.active = false;
        clearBranchSession();
      },
    } satisfies BranchReaderComponent);
  });
});
