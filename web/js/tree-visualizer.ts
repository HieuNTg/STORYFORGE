/**
 * tree-visualizer.ts — SVG tree layout and rendering for branch visualization.
 * Pure functions: compute node positions from flat tree data, render as SVG.
 * No external dependencies.
 */

interface TreeNodeData {
  id: string;
  text: string;
  choices?: string[];
  parent: string | null;
  child_ids: string[];
  depth: number;
}

interface TreeApiResponse {
  session_id: string;
  root: string;
  current: string;
  nodes: Record<string, TreeNodeData>;
}

interface LayoutNode {
  id: string;
  x: number;
  y: number;
  label: string;
  isCurrent: boolean;
  depth: number;
}

interface LayoutEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface TreeLayout {
  nodes: LayoutNode[];
  edges: LayoutEdge[];
  width: number;
  height: number;
}

const TREE_H_SPACING = 100;
const TREE_V_SPACING = 80;
const TREE_NODE_RADIUS = 18;
const TREE_PADDING = 40;

function computeTreeLayout(data: TreeApiResponse): TreeLayout {
  const allNodes = data.nodes;
  const rootId = data.root;
  const currentId = data.current;

  if (!rootId || !allNodes[rootId]) {
    return { nodes: [], edges: [], width: 0, height: 0 };
  }

  const layoutNodes: LayoutNode[] = [];
  const layoutEdges: LayoutEdge[] = [];
  let leafIndex = 0;

  function computeSubtreeWidth(nodeId: string): number {
    const node = allNodes[nodeId];
    if (!node || node.child_ids.length === 0) return 1;
    let total = 0;
    for (const childId of node.child_ids) {
      total += computeSubtreeWidth(childId);
    }
    return total;
  }

  function layoutDFS(nodeId: string, depth: number, xOffset: number): number {
    const node = allNodes[nodeId];
    if (!node) return xOffset;

    const label = node.text.slice(0, 16) + (node.text.length > 16 ? '...' : '');

    if (node.child_ids.length === 0) {
      const x = TREE_PADDING + leafIndex * TREE_H_SPACING;
      const y = TREE_PADDING + depth * TREE_V_SPACING;
      layoutNodes.push({ id: nodeId, x, y, label, isCurrent: nodeId === currentId, depth });
      leafIndex++;
      return x;
    }

    const childXPositions: number[] = [];
    for (const childId of node.child_ids) {
      const childX = layoutDFS(childId, depth + 1, xOffset);
      childXPositions.push(childX);
    }

    const x = childXPositions.reduce((a, b) => a + b, 0) / childXPositions.length;
    const y = TREE_PADDING + depth * TREE_V_SPACING;
    layoutNodes.push({ id: nodeId, x, y, label, isCurrent: nodeId === currentId, depth });

    for (const childId of node.child_ids) {
      const childNode = layoutNodes.find(n => n.id === childId);
      if (childNode) {
        layoutEdges.push({ x1: x, y1: y, x2: childNode.x, y2: childNode.y });
      }
    }

    return x;
  }

  layoutDFS(rootId, 0, 0);

  const maxX = Math.max(...layoutNodes.map(n => n.x), 0) + TREE_PADDING;
  const maxY = Math.max(...layoutNodes.map(n => n.y), 0) + TREE_PADDING;

  return { nodes: layoutNodes, edges: layoutEdges, width: maxX, height: maxY };
}

interface TreeVisualizerComponent {
  showTree: boolean;
  treeLayout: TreeLayout | null;
  treeLoading: boolean;
  treeError: string;
  _sessionId: string | null;
  init(): void;
  destroy(): void;
  setSession(sessionId: string | null): void;
  toggleTree(sessionId: string | null): Promise<void>;
  refreshTree(sessionId: string | null): Promise<void>;
  gotoNode(sessionId: string | null, nodeId: string): Promise<TreeNodeData | null>;
  readonly viewBox: string;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('treeVisualizer', () => {
    let navHandler: (() => void) | null = null;

    return {
      showTree: false,
      treeLayout: null as TreeLayout | null,
      treeLoading: false,
      treeError: '',
      _sessionId: null as string | null,

      init(this: TreeVisualizerComponent) {
        navHandler = () => { this.refreshTree(this._sessionId); };
        document.addEventListener('branch:navigated', navHandler);
      },

      destroy() {
        if (navHandler) document.removeEventListener('branch:navigated', navHandler);
      },

      setSession(this: TreeVisualizerComponent, sessionId: string | null) {
        this._sessionId = sessionId;
      },

      async toggleTree(this: TreeVisualizerComponent, sessionId: string | null) {
        this._sessionId = sessionId;
        this.showTree = !this.showTree;
        if (this.showTree) {
          await this.refreshTree(sessionId);
        }
      },

      async refreshTree(this: TreeVisualizerComponent, sessionId: string | null) {
        if (!sessionId || !this.showTree) return;
        this.treeLoading = true;
        this.treeError = '';
        try {
          const res = await fetch(`/api/branch/${sessionId}/tree`);
          if (!res.ok) {
            this.treeError = `Failed to load tree (${res.status})`;
            return;
          }
          const d: TreeApiResponse = await res.json();
          this.treeLayout = computeTreeLayout(d);
        } catch (e) {
          this.treeError = (e as Error).message || 'Failed to load tree';
        } finally {
          this.treeLoading = false;
        }
      },

      async gotoNode(sessionId: string | null, nodeId: string) {
        if (!sessionId) return null;
        try {
          const res = await fetch(`/api/branch/${sessionId}/goto`, {
            method: 'POST',
            headers: mutationHeaders(),
            body: JSON.stringify({ node_id: nodeId }),
          });
          if (!res.ok) return null;
          const d = await res.json();
          return d.node;
        } catch {
          return null;
        }
      },

      get viewBox(): string {
        const self = this as unknown as TreeVisualizerComponent;
        if (!self.treeLayout) return '0 0 200 100';
        return `0 0 ${self.treeLayout.width} ${self.treeLayout.height}`;
      },
    };
  });
});
