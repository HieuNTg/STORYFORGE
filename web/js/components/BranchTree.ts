/**
 * BranchTree — Alpine.data factory wrapping a d3-force simulation + Canvas renderer.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.x (BranchTree)
 *       plans/260512-1949-uiux-prd-implementation/03-engineering-plan.md §4.1
 *
 * Architecture (mirrors CharacterGraph pattern from M2):
 *   - Simulation lives in the factory; nodes carry mutable x/y/vx/vy.
 *   - Template wires init()/destroy() and passes the <canvas> ref via attachCanvas().
 *   - The factory owns the rAF loop and redraws on every tick.
 *   - A parallel screen-reader <ul> is exposed via srEntries (a11y R4 requirement).
 *   - Minimap is rendered on a second canvas (minimapCanvas ref). If not wired,
 *     the text fallback "Branch X of Y" is exposed via minimapLabel.
 *
 * D3 footprint: d3-force only. No d3-selection, no d3-zoom, no d3-drag.
 *   - Pan/zoom: pointer events on the canvas (same as CharacterGraph).
 *   - d3-force lays out nodes; Canvas draws them.
 *
 * Reduced-motion: simulation settles synchronously (300-tick loop) before first
 *   paint; no rAF animation. Matches CharacterGraph._runToRest().
 *
 * Keyboard nav:
 *   - ArrowRight / ArrowDown → first child of focused node.
 *   - ArrowLeft / ArrowUp   → parent of focused node.
 *   - ArrowLeft on root     → no-op.
 *   - Enter / Space         → navigate (dispatch sf:branch-navigate).
 *   - Tab cycles tree canvas → minimap → metadata panel (managed by tabIndex
 *     on the canvas elements; the component only sets/clears focus classes).
 *
 * Imported unconditionally (Forge UI shipped on, STORYFORGE_FORGE_UI removed).
 *   The legacy treeVisualizer (tree-visualizer.ts) remains untouched.
 */

import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  forceY,
} from 'd3-force';
import type { Simulation, SimulationNodeDatum, SimulationLinkDatum, ForceLink } from 'd3-force';

// ── Public types ──────────────────────────────────────────────────────────────

export interface BranchNode {
  id: string;
  /** Short display text (≤ 30 chars recommended). */
  label: string;
  /** Node id of the parent, or null for the root. */
  parentId: string | null;
  /** Depth in the tree (root = 0). */
  depth: number;
  /** True when this node is the current navigation position. */
  isCurrent?: boolean;
}

export interface BranchEdge {
  sourceId: string;
  targetId: string;
}

export interface BranchTreeProps {
  nodes?: BranchNode[];
  currentNodeId?: string | null;
  /** Called when user clicks/activates a node. */
  onNavigate?: (nodeId: string) => void;
  /** Canvas width in CSS pixels. Default 800. */
  width?: number;
  /** Canvas height in CSS pixels. Default 500. */
  height?: number;
  /** Minimap canvas width in CSS pixels. Default 160. */
  minimapWidth?: number;
  /** Minimap canvas height in CSS pixels. Default 100. */
  minimapHeight?: number;
  prefersReducedMotion?: boolean;
}

// ── Internal simulation types ─────────────────────────────────────────────────

interface SimNode extends SimulationNodeDatum {
  id: string;
  label: string;
  parentId: string | null;
  depth: number;
  isCurrent: boolean;
  /** Fixed when the user drags and releases (toggle). */
  _pinned: boolean;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  sourceId: string;
  targetId: string;
}

// ── SR (screen-reader) entry type ────────────────────────────────────────────

export interface BranchSrEntry {
  id: string;
  label: string;
  depth: number;
  isCurrent: boolean;
  parentId: string | null;
  childIds: string[];
}

// ── Component public interface ────────────────────────────────────────────────

export interface BranchTreeComponent {
  // State
  nodes: BranchNode[];
  currentNodeId: string | null;
  width: number;
  height: number;
  minimapWidth: number;
  minimapHeight: number;
  prefersReducedMotion: boolean;
  canvas: HTMLCanvasElement | null;
  minimapCanvas: HTMLCanvasElement | null;
  simulation: Simulation<SimNode, SimLink> | null;
  _simNodes: SimNode[];
  _simLinks: SimLink[];
  _rafHandle: number | null;
  _dragging: SimNode | null;
  _dragPinToggle: boolean;
  /** Viewport pan/zoom state. */
  _panX: number;
  _panY: number;
  _scale: number;
  /** Keyboard-focused node id. */
  focusedNodeId: string | null;

  // Minimap text fallback
  readonly minimapLabel: string;
  // SR list
  readonly srEntries: BranchSrEntry[];
  // Total branch count
  readonly branchCount: number;
  // Current branch index (1-based depth-first order)
  readonly currentBranchIndex: number;

  // Methods
  setData(nodes: BranchNode[], currentNodeId?: string | null): void;
  attachCanvas(canvas: HTMLCanvasElement | null): void;
  attachMinimapCanvas(canvas: HTMLCanvasElement | null): void;
  draw(): void;
  drawMinimap(): void;
  handlePointerDown(event: PointerEvent): void;
  handlePointerMove(event: PointerEvent): void;
  handlePointerUp(event: PointerEvent): void;
  handleWheel(event: WheelEvent): void;
  handleKeyDown(event: KeyboardEvent): void;
  navigateTo(nodeId: string): void;
  /** Focus a node by id (for keyboard nav). */
  focusNode(nodeId: string | null): void;
  step(): void;
  startSimulation(): void;
  stopSimulation(): void;
  init(): void;
  destroy(): void;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const NODE_R = 14;
/** Vertical spread force — pushes deeper nodes downward. */
const DEPTH_Y_STRENGTH = 0.4;
const DEPTH_Y_SPACING = 90;

const COLOR_CURRENT = '#F59E0B';
const COLOR_DEFAULT = '#3B82F6';
const COLOR_FOCUSED = '#8B5CF6';
const COLOR_EDGE = '#6B7280';
const COLOR_NODE_FILL = '#1F2937';
const COLOR_LABEL = '#F9FAFB';

// ── Helpers ───────────────────────────────────────────────────────────────────

function detectReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false;
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches === true;
  } catch {
    return false;
  }
}

function buildEdges(nodes: BranchNode[]): BranchEdge[] {
  const edges: BranchEdge[] = [];
  for (const n of nodes) {
    if (n.parentId !== null) {
      edges.push({ sourceId: n.parentId, targetId: n.id });
    }
  }
  return edges;
}

function reconcileSimNodes(prev: SimNode[], next: BranchNode[], currentId: string | null): SimNode[] {
  const prevById = new Map(prev.map((n) => [n.id, n]));
  return next.map((n) => {
    const existing = prevById.get(n.id);
    if (existing) {
      existing.label = n.label;
      existing.depth = n.depth;
      existing.isCurrent = n.id === currentId;
      return existing;
    }
    return {
      id: n.id,
      label: n.label,
      parentId: n.parentId,
      depth: n.depth,
      isCurrent: n.id === currentId,
      _pinned: false,
    } as SimNode;
  });
}

function reconcileSimLinks(simNodes: SimNode[], edges: BranchEdge[]): SimLink[] {
  const byId = new Map(simNodes.map((n) => [n.id, n]));
  const out: SimLink[] = [];
  for (const e of edges) {
    const src = byId.get(e.sourceId);
    const tgt = byId.get(e.targetId);
    if (!src || !tgt) continue;
    out.push({ source: src, target: tgt, sourceId: e.sourceId, targetId: e.targetId });
  }
  return out;
}

/** Convert canvas-space pointer to world-space coordinates. */
function toWorld(
  cx: number,
  cy: number,
  panX: number,
  panY: number,
  scale: number,
): { wx: number; wy: number } {
  return { wx: (cx - panX) / scale, wy: (cy - panY) / scale };
}

function findNearestNode(wx: number, wy: number, simNodes: SimNode[]): SimNode | null {
  let nearest: SimNode | null = null;
  let nearestD2 = (NODE_R * 2) * (NODE_R * 2);
  for (const n of simNodes) {
    if (typeof n.x !== 'number' || typeof n.y !== 'number') continue;
    const dx = n.x - wx;
    const dy = n.y - wy;
    const d2 = dx * dx + dy * dy;
    if (d2 < nearestD2) {
      nearestD2 = d2;
      nearest = n;
    }
  }
  return nearest;
}

// ── Factory ───────────────────────────────────────────────────────────────────

export function branchTree(props: BranchTreeProps = {}): BranchTreeComponent {
  const width = Number.isFinite(props.width) ? (props.width as number) : 800;
  const height = Number.isFinite(props.height) ? (props.height as number) : 500;
  const minimapWidth = Number.isFinite(props.minimapWidth) ? (props.minimapWidth as number) : 160;
  const minimapHeight = Number.isFinite(props.minimapHeight) ? (props.minimapHeight as number) : 100;
  const reducedMotion =
    typeof props.prefersReducedMotion === 'boolean' ? props.prefersReducedMotion : detectReducedMotion();

  const nodes: BranchNode[] = Array.isArray(props.nodes) ? props.nodes.slice() : [];
  const currentNodeId: string | null =
    typeof props.currentNodeId === 'string' ? props.currentNodeId : null;

  return {
    nodes,
    currentNodeId,
    width,
    height,
    minimapWidth,
    minimapHeight,
    prefersReducedMotion: reducedMotion,
    canvas: null,
    minimapCanvas: null,
    simulation: null,
    _simNodes: [],
    _simLinks: [],
    _rafHandle: null,
    _dragging: null,
    _dragPinToggle: false,
    _panX: 0,
    _panY: 0,
    _scale: 1,
    focusedNodeId: null,

    // ── Derived properties ────────────────────────────────────────────────

    get minimapLabel(): string {
      const total = this.nodes.length;
      if (total === 0) return '';
      const cur = this.nodes.find((n) => n.id === this.currentNodeId);
      if (!cur) return `${total} branches`;
      // 1-based index in DFS order
      const idx = this.nodes.findIndex((n) => n.id === this.currentNodeId) + 1;
      return `Branch ${idx} of ${total}`;
    },

    get branchCount(): number {
      return this.nodes.length;
    },

    get currentBranchIndex(): number {
      if (!this.currentNodeId) return 0;
      return this.nodes.findIndex((n) => n.id === this.currentNodeId) + 1;
    },

    get srEntries(): BranchSrEntry[] {
      const childMap = new Map<string, string[]>();
      for (const n of this.nodes) {
        if (n.parentId) {
          const siblings = childMap.get(n.parentId) ?? [];
          siblings.push(n.id);
          childMap.set(n.parentId, siblings);
        }
      }
      return this.nodes.map((n) => ({
        id: n.id,
        label: n.label,
        depth: n.depth,
        isCurrent: n.id === this.currentNodeId,
        parentId: n.parentId,
        childIds: childMap.get(n.id) ?? [],
      }));
    },

    // ── Data management ───────────────────────────────────────────────────

    setData(nextNodes: BranchNode[], nextCurrentId?: string | null): void {
      this.nodes = Array.isArray(nextNodes) ? nextNodes.slice() : [];
      if (nextCurrentId !== undefined) this.currentNodeId = nextCurrentId ?? null;

      this._simNodes = reconcileSimNodes(this._simNodes, this.nodes, this.currentNodeId);
      const edges = buildEdges(this.nodes);
      this._simLinks = reconcileSimLinks(this._simNodes, edges);

      if (this.simulation) {
        this.simulation.nodes(this._simNodes);
        const lf = this.simulation.force('link') as ForceLink<SimNode, SimLink> | undefined;
        lf?.links(this._simLinks);
        const yf = this.simulation.force('depth-y') as ReturnType<typeof forceY> | undefined;
        if (yf) {
          (yf as ReturnType<typeof forceY<SimNode>>).y((d: SimNode) => d.depth * DEPTH_Y_SPACING + 60);
        }
        this.simulation.alpha(0.6).restart();
        if (this.prefersReducedMotion) this._runToRest();
      }
    },

    // ── Canvas attachment ─────────────────────────────────────────────────

    attachCanvas(canvas: HTMLCanvasElement | null): void {
      this.canvas = canvas;
      if (canvas) this.draw();
    },

    attachMinimapCanvas(canvas: HTMLCanvasElement | null): void {
      this.minimapCanvas = canvas;
      if (canvas) this.drawMinimap();
    },

    // ── Draw main canvas ─────────────────────────────────────────────────

    draw(): void {
      const canvas = this.canvas;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
      const cssW = this.width;
      const cssH = this.height;
      if (canvas.width !== cssW * dpr) canvas.width = cssW * dpr;
      if (canvas.height !== cssH * dpr) canvas.height = cssH * dpr;

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);

      // Apply pan/zoom transform.
      ctx.save();
      ctx.translate(this._panX, this._panY);
      ctx.scale(this._scale, this._scale);

      // Edges first.
      ctx.strokeStyle = COLOR_EDGE;
      ctx.globalAlpha = 0.5;
      ctx.lineWidth = 1.5;
      for (const link of this._simLinks) {
        const s = link.source as SimNode;
        const t = link.target as SimNode;
        if (typeof s.x !== 'number' || typeof t.x !== 'number') continue;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y ?? 0);
        ctx.lineTo(t.x, t.y ?? 0);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // Nodes.
      for (const node of this._simNodes) {
        if (typeof node.x !== 'number' || typeof node.y !== 'number') continue;
        const isCurrent = node.id === this.currentNodeId;
        const isFocused = node.id === this.focusedNodeId;
        const ringColor = isCurrent ? COLOR_CURRENT : isFocused ? COLOR_FOCUSED : COLOR_DEFAULT;

        ctx.fillStyle = COLOR_NODE_FILL;
        ctx.strokeStyle = ringColor;
        ctx.lineWidth = isCurrent || isFocused ? 3 : 1.5;
        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_R, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        // Pin indicator.
        if (node._pinned) {
          ctx.fillStyle = COLOR_CURRENT;
          ctx.beginPath();
          ctx.arc(node.x + NODE_R - 4, node.y - NODE_R + 4, 3, 0, Math.PI * 2);
          ctx.fill();
        }

        // Label.
        ctx.fillStyle = COLOR_LABEL;
        ctx.font = `${isCurrent ? 'bold ' : ''}10px system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        const shortLabel = node.label.length > 18 ? node.label.slice(0, 17) + '…' : node.label;
        ctx.fillText(shortLabel, node.x, node.y + NODE_R + 3);
      }

      ctx.restore();
    },

    // ── Draw minimap ─────────────────────────────────────────────────────

    drawMinimap(): void {
      const mc = this.minimapCanvas;
      if (!mc || this._simNodes.length === 0) return;
      const ctx = mc.getContext('2d');
      if (!ctx) return;

      const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
      if (mc.width !== this.minimapWidth * dpr) mc.width = this.minimapWidth * dpr;
      if (mc.height !== this.minimapHeight * dpr) mc.height = this.minimapHeight * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, this.minimapWidth, this.minimapHeight);

      // Compute world bounds.
      const xs = this._simNodes.filter((n) => typeof n.x === 'number').map((n) => n.x as number);
      const ys = this._simNodes.filter((n) => typeof n.y === 'number').map((n) => n.y as number);
      if (xs.length === 0) return;
      const wMinX = Math.min(...xs) - NODE_R;
      const wMaxX = Math.max(...xs) + NODE_R;
      const wMinY = Math.min(...ys) - NODE_R;
      const wMaxY = Math.max(...ys) + NODE_R;
      const worldW = wMaxX - wMinX || 1;
      const worldH = wMaxY - wMinY || 1;

      const mmW = this.minimapWidth;
      const mmH = this.minimapHeight;
      const scaleX = mmW / worldW;
      const scaleY = mmH / worldH;
      const mmScale = Math.min(scaleX, scaleY) * 0.85;

      const offsetX = (mmW - worldW * mmScale) / 2 - wMinX * mmScale;
      const offsetY = (mmH - worldH * mmScale) / 2 - wMinY * mmScale;

      // Background.
      ctx.fillStyle = 'rgba(15,18,25,0.7)';
      ctx.fillRect(0, 0, mmW, mmH);

      // Edges.
      ctx.strokeStyle = COLOR_EDGE;
      ctx.globalAlpha = 0.4;
      ctx.lineWidth = 0.5;
      for (const link of this._simLinks) {
        const s = link.source as SimNode;
        const t = link.target as SimNode;
        if (typeof s.x !== 'number' || typeof t.x !== 'number') continue;
        ctx.beginPath();
        ctx.moveTo(s.x * mmScale + offsetX, (s.y ?? 0) * mmScale + offsetY);
        ctx.lineTo(t.x * mmScale + offsetX, (t.y ?? 0) * mmScale + offsetY);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // Nodes.
      const mmNodeR = Math.max(2, NODE_R * mmScale);
      for (const node of this._simNodes) {
        if (typeof node.x !== 'number' || typeof node.y !== 'number') continue;
        const isCurrent = node.id === this.currentNodeId;
        ctx.fillStyle = isCurrent ? COLOR_CURRENT : COLOR_DEFAULT;
        ctx.beginPath();
        ctx.arc(node.x * mmScale + offsetX, (node.y ?? 0) * mmScale + offsetY, mmNodeR, 0, Math.PI * 2);
        ctx.fill();
      }

      // Viewport indicator — show what portion of the world is visible in the main canvas.
      const vpLeft = (-this._panX / this._scale) * mmScale + offsetX;
      const vpTop = (-this._panY / this._scale) * mmScale + offsetY;
      const vpWidth = (this.width / this._scale) * mmScale;
      const vpHeight = (this.height / this._scale) * mmScale;
      ctx.strokeStyle = '#FFFFFF';
      ctx.globalAlpha = 0.6;
      ctx.lineWidth = 1;
      ctx.strokeRect(vpLeft, vpTop, vpWidth, vpHeight);
      ctx.globalAlpha = 1;
    },

    // ── Pointer events (pan/zoom + drag) ─────────────────────────────────

    handlePointerDown(event: PointerEvent): void {
      if (!this.canvas) return;
      const rect = this.canvas.getBoundingClientRect();
      const cx = event.clientX - rect.left;
      const cy = event.clientY - rect.top;
      const { wx, wy } = toWorld(cx, cy, this._panX, this._panY, this._scale);

      const hit = findNearestNode(wx, wy, this._simNodes);
      if (hit) {
        this._dragging = hit;
        this._dragPinToggle = !hit._pinned;
        hit.fx = hit.x;
        hit.fy = hit.y;
        this.simulation?.alphaTarget(0.3).restart();
      } else {
        // Start pan.
        this._dragging = null;
        (this.canvas as HTMLCanvasElement & { _panStart?: { cx: number; cy: number; px: number; py: number } })._panStart = {
          cx,
          cy,
          px: this._panX,
          py: this._panY,
        };
      }
    },

    handlePointerMove(event: PointerEvent): void {
      if (!this.canvas) return;
      const rect = this.canvas.getBoundingClientRect();
      const cx = event.clientX - rect.left;
      const cy = event.clientY - rect.top;

      if (this._dragging) {
        const { wx, wy } = toWorld(cx, cy, this._panX, this._panY, this._scale);
        this._dragging.fx = wx;
        this._dragging.fy = wy;
      } else {
        const ps = (this.canvas as HTMLCanvasElement & { _panStart?: { cx: number; cy: number; px: number; py: number } })._panStart;
        if (ps) {
          this._panX = ps.px + (cx - ps.cx);
          this._panY = ps.py + (cy - ps.cy);
          this.draw();
          this.drawMinimap();
        }
      }
    },

    handlePointerUp(event: PointerEvent): void {
      if (this._dragging) {
        const node = this._dragging;
        node._pinned = this._dragPinToggle;
        if (node._pinned) {
          // Keep fx/fy — node stays fixed.
        } else {
          node.fx = null;
          node.fy = null;
        }
        this.simulation?.alphaTarget(0);
        this._dragging = null;
      } else if (this.canvas) {
        // Click without drag — check for node hit (navigate).
        const rect = this.canvas.getBoundingClientRect();
        const cx = event.clientX - rect.left;
        const cy = event.clientY - rect.top;
        const ps = (this.canvas as HTMLCanvasElement & { _panStart?: { cx: number; cy: number; px: number; py: number } })._panStart;
        if (ps) {
          const moved = Math.abs(cx - ps.cx) + Math.abs(cy - ps.cy) < 4;
          if (moved) {
            const { wx, wy } = toWorld(cx, cy, this._panX, this._panY, this._scale);
            const hit = findNearestNode(wx, wy, this._simNodes);
            if (hit) this.navigateTo(hit.id);
          }
          delete (this.canvas as HTMLCanvasElement & { _panStart?: unknown })._panStart;
        }
      }
    },

    handleWheel(event: WheelEvent): void {
      event.preventDefault();
      const delta = event.deltaY > 0 ? 0.9 : 1.1;
      const newScale = Math.max(0.3, Math.min(3, this._scale * delta));
      if (!this.canvas) {
        this._scale = newScale;
        return;
      }
      const rect = this.canvas.getBoundingClientRect();
      const cx = event.clientX - rect.left;
      const cy = event.clientY - rect.top;
      // Zoom around cursor.
      this._panX = cx - (cx - this._panX) * (newScale / this._scale);
      this._panY = cy - (cy - this._panY) * (newScale / this._scale);
      this._scale = newScale;
      this.draw();
      this.drawMinimap();
    },

    // ── Keyboard navigation ───────────────────────────────────────────────

    handleKeyDown(event: KeyboardEvent): void {
      const key = event.key;
      if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp', 'Enter', ' '].includes(key)) return;
      event.preventDefault();

      const focusId = this.focusedNodeId ?? this.currentNodeId ?? (this._simNodes[0]?.id ?? null);
      if (!focusId) return;

      const entry = this.srEntries.find((e) => e.id === focusId);
      if (!entry) return;

      if (key === 'ArrowRight' || key === 'ArrowDown') {
        // Move to first child.
        const firstChild = entry.childIds[0] ?? null;
        if (firstChild) this.focusNode(firstChild);
      } else if (key === 'ArrowLeft' || key === 'ArrowUp') {
        // Move to parent.
        if (entry.parentId) this.focusNode(entry.parentId);
      } else if (key === 'Enter' || key === ' ') {
        this.navigateTo(focusId);
      }
    },

    focusNode(nodeId: string | null): void {
      this.focusedNodeId = nodeId;
      this.draw();
      this.drawMinimap();
    },

    // ── Navigation dispatch ───────────────────────────────────────────────

    navigateTo(nodeId: string): void {
      if (typeof props.onNavigate === 'function') {
        try {
          props.onNavigate(nodeId);
        } catch {
          // silent
        }
      }
      // Also dispatch a DOM event so Alpine templates can listen with @sf-branch-navigate.window.
      if (typeof document !== 'undefined') {
        document.dispatchEvent(
          new CustomEvent('sf:branch-navigate', { detail: { nodeId }, bubbles: true }),
        );
      }
    },

    // ── Simulation lifecycle ──────────────────────────────────────────────

    step(): void {
      this.simulation?.tick();
      this.draw();
      this.drawMinimap();
    },

    startSimulation(): void {
      if (!this.simulation) return;
      if (this.prefersReducedMotion) {
        this._runToRest();
        return;
      }
      const loop = (): void => {
        this.draw();
        this.drawMinimap();
        if (typeof requestAnimationFrame === 'function') {
          this._rafHandle = requestAnimationFrame(loop);
        }
      };
      if (typeof requestAnimationFrame === 'function') {
        this._rafHandle = requestAnimationFrame(loop);
      }
    },

    stopSimulation(): void {
      if (this._rafHandle !== null && typeof cancelAnimationFrame === 'function') {
        cancelAnimationFrame(this._rafHandle);
      }
      this._rafHandle = null;
      this.simulation?.stop();
    },

    init(): void {
      this._simNodes = reconcileSimNodes([], this.nodes, this.currentNodeId);

      // Seed positions spread by depth to give the tree a natural top-down layout
      // before force-settle, which dramatically reduces visible flicker.
      const depthGroups = new Map<number, SimNode[]>();
      for (const n of this._simNodes) {
        const g = depthGroups.get(n.depth) ?? [];
        g.push(n);
        depthGroups.set(n.depth, g);
      }
      for (const [depth, group] of depthGroups) {
        const colW = this.width / (group.length + 1);
        group.forEach((n, i) => {
          n.x = colW * (i + 1);
          n.y = 60 + depth * DEPTH_Y_SPACING;
        });
      }

      const edges = buildEdges(this.nodes);
      this._simLinks = reconcileSimLinks(this._simNodes, edges);

      this.simulation = forceSimulation<SimNode, SimLink>(this._simNodes)
        .force(
          'link',
          forceLink<SimNode, SimLink>(this._simLinks)
            .id((d: SimNode) => d.id)
            .distance(80)
            .strength(0.5),
        )
        .force('charge', forceManyBody().strength(-200))
        .force('center', forceCenter(this.width / 2, this.height / 2).strength(0.05))
        .force('collide', forceCollide(NODE_R + 6))
        .force(
          'depth-y',
          forceY<SimNode>((d: SimNode) => d.depth * DEPTH_Y_SPACING + 60).strength(DEPTH_Y_STRENGTH),
        )
        .on('tick', () => {
          this.draw();
          this.drawMinimap();
        });

      if (this.prefersReducedMotion) {
        this._runToRest();
      } else {
        this.startSimulation();
      }
    },

    destroy(): void {
      this.stopSimulation();
      this.simulation = null;
    },

    /**
     * Synchronously settle the simulation without rAF.
     * Used in prefers-reduced-motion mode (mirrors CharacterGraph._runToRest).
     */
    _runToRest(): void {
      const sim = this.simulation;
      if (!sim) return;
      sim.stop();
      for (let i = 0; i < 300; i++) {
        sim.tick();
        if (sim.alpha() < sim.alphaMin()) break;
      }
      this.draw();
      this.drawMinimap();
    },
  } as BranchTreeComponent & { _runToRest: () => void };
}
