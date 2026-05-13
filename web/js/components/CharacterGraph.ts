/**
 * CharacterGraph — Alpine.data factory wrapping a d3-force simulation +
 * Canvas renderer.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §4.3
 *
 * Architecture:
 *   - Simulation lives in the factory; nodes carry mutable x/y/vx/vy.
 *   - Template wires `init()` and `destroy()` and passes the <canvas> ref
 *     via attachCanvas(); the factory owns the rAF loop and redraws.
 *   - A parallel screen-reader list (`srEntries`) is exposed so the
 *     template can render the a11y mirror (<ul role="list" hidden>).
 *
 * Edges arrive as `relationships` props. The audit (D2) chose a
 * co-occurrence heuristic to derive them from done.data.draft — see
 * web/js/stores/character-edges.ts; that derivation is the parent's job.
 * This component renders whatever edge list it's given.
 *
 * D3 footprint: d3-force only. No d3-selection (Canvas direct draw), no
 * d3-zoom (pan/zoom is reserved for BranchTree). Drag is hand-rolled via
 * pointer events on the canvas (saves the d3-drag bundle).
 *
 * Reduced-motion: simulation runs `alphaMin` ticks synchronously and
 * stops; no continuous animation.
 */

import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from 'd3-force';
import type {
  Simulation,
  SimulationNodeDatum,
  SimulationLinkDatum,
  ForceLink,
} from 'd3-force';

export type RelationshipType = 'ally' | 'enemy' | 'rival' | 'neutral';

export interface CharacterNode {
  id: string;
  name: string;
  portrait?: string;
}

export interface CharacterEdge {
  sourceId: string;
  targetId: string;
  type: RelationshipType;
  /** 0..1 — drives edge stroke width and opacity. */
  intensity: number;
}

export interface CharacterGraphProps {
  characters?: CharacterNode[];
  relationships?: CharacterEdge[];
  compact?: boolean;
  /** When true, pointer drag is enabled. Default true. */
  interactive?: boolean;
  /** Canvas width in CSS pixels. Default 600. */
  width?: number;
  /** Canvas height in CSS pixels. Default 400. */
  height?: number;
  prefersReducedMotion?: boolean;
}

/** Mutable simulation node — extends d3's SimulationNodeDatum with our id/name. */
interface SimNode extends SimulationNodeDatum {
  id: string;
  name: string;
  portrait?: string;
}

/** Link with our edge metadata layered on. */
interface SimLink extends SimulationLinkDatum<SimNode> {
  sourceId: string;
  targetId: string;
  type: RelationshipType;
  intensity: number;
}

export interface CharacterGraphComponent {
  characters: CharacterNode[];
  relationships: CharacterEdge[];
  compact: boolean;
  interactive: boolean;
  width: number;
  height: number;
  prefersReducedMotion: boolean;
  /** Set by attachCanvas(). Null when the template hasn't wired the ref. */
  canvas: HTMLCanvasElement | null;
  /** d3-force simulation. Created on init(). */
  simulation: Simulation<SimNode, SimLink> | null;
  /** Current simulation node array — mutated each tick. */
  nodes: SimNode[];
  links: SimLink[];
  /** rAF handle for the redraw loop. */
  _rafHandle: number | null;
  /** Currently-dragged node, if any. */
  _dragging: SimNode | null;

  readonly srEntries: Array<{ name: string; edges: Array<{ otherName: string; type: RelationshipType; intensity: number }> }>;

  setData(characters: CharacterNode[], relationships: CharacterEdge[]): void;
  attachCanvas(canvas: HTMLCanvasElement | null): void;
  draw(): void;
  /** Manually advance the simulation by one tick. Test hook. */
  step(): void;
  startSimulation(): void;
  stopSimulation(): void;

  /** Pointer handlers — wired by the template via @pointerdown etc. */
  handlePointerDown(event: PointerEvent): void;
  handlePointerMove(event: PointerEvent): void;
  handlePointerUp(event: PointerEvent): void;

  init(): void;
  destroy(): void;
}

const EDGE_COLOR: Readonly<Record<RelationshipType, string>> = Object.freeze({
  ally: '#10B981',
  enemy: '#F43F5E',
  rival: '#F59E0B',
  neutral: '#9CA3AF',
});

const NODE_RADIUS = 18;

function detectReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches === true;
  } catch {
    return false;
  }
}

/** Build SimNode list, preserving existing positions when an id is already known. */
function reconcileNodes(prev: SimNode[], chars: CharacterNode[]): SimNode[] {
  const prevById = new Map(prev.map((n) => [n.id, n]));
  return chars.map((c) => {
    const existing = prevById.get(c.id);
    if (existing) {
      existing.name = c.name;
      existing.portrait = c.portrait;
      return existing;
    }
    return { id: c.id, name: c.name, portrait: c.portrait };
  });
}

function reconcileLinks(nodes: SimNode[], rels: CharacterEdge[]): SimLink[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const out: SimLink[] = [];
  for (const r of rels) {
    const source = byId.get(r.sourceId);
    const target = byId.get(r.targetId);
    if (!source || !target) continue;
    const link: SimLink = {
      source,
      target,
      sourceId: r.sourceId,
      targetId: r.targetId,
      type: r.type,
      intensity: r.intensity,
    };
    out.push(link);
  }
  return out;
}

export function characterGraph(props: CharacterGraphProps = {}): CharacterGraphComponent {
  const characters = Array.isArray(props.characters) ? props.characters.slice() : [];
  const relationships = Array.isArray(props.relationships) ? props.relationships.slice() : [];
  const width = Number.isFinite(props.width) ? (props.width as number) : 600;
  const height = Number.isFinite(props.height) ? (props.height as number) : 400;
  const reducedMotion =
    typeof props.prefersReducedMotion === 'boolean'
      ? props.prefersReducedMotion
      : detectReducedMotion();

  return {
    characters,
    relationships,
    compact: props.compact === true,
    interactive: props.interactive !== false,
    width,
    height,
    prefersReducedMotion: reducedMotion,
    canvas: null,
    simulation: null,
    nodes: [],
    links: [],
    _rafHandle: null,
    _dragging: null,

    get srEntries(): Array<{ name: string; edges: Array<{ otherName: string; type: RelationshipType; intensity: number }> }> {
      const byId = new Map(this.characters.map((c) => [c.id, c.name] as const));
      return this.characters.map((c) => {
        const edges = this.relationships
          .filter((r) => r.sourceId === c.id || r.targetId === c.id)
          .map((r) => {
            const otherId = r.sourceId === c.id ? r.targetId : r.sourceId;
            return {
              otherName: byId.get(otherId) ?? otherId,
              type: r.type,
              intensity: r.intensity,
            };
          });
        return { name: c.name, edges };
      });
    },

    setData(nextChars: CharacterNode[], nextRels: CharacterEdge[]): void {
      this.characters = Array.isArray(nextChars) ? nextChars.slice() : [];
      this.relationships = Array.isArray(nextRels) ? nextRels.slice() : [];
      this.nodes = reconcileNodes(this.nodes, this.characters);
      this.links = reconcileLinks(this.nodes, this.relationships);
      if (this.simulation) {
        this.simulation.nodes(this.nodes);
        const linkForce = this.simulation.force('link') as ForceLink<SimNode, SimLink> | undefined;
        linkForce?.links(this.links);
        this.simulation.alpha(0.6).restart();
        if (this.prefersReducedMotion) {
          this._runToRest();
        }
      }
    },

    attachCanvas(canvas: HTMLCanvasElement | null): void {
      this.canvas = canvas;
      if (canvas) this.draw();
    },

    draw(): void {
      const canvas = this.canvas;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;

      const dpr = typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1;
      if (canvas.width !== this.width * dpr) canvas.width = this.width * dpr;
      if (canvas.height !== this.height * dpr) canvas.height = this.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, this.width, this.height);

      // Edges first so nodes paint over them.
      for (const link of this.links) {
        const s = link.source as SimNode;
        const t = link.target as SimNode;
        if (typeof s.x !== 'number' || typeof t.x !== 'number') continue;
        ctx.strokeStyle = EDGE_COLOR[link.type];
        ctx.globalAlpha = 0.3 + 0.7 * link.intensity;
        ctx.lineWidth = 1 + 3 * link.intensity;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y ?? 0);
        ctx.lineTo(t.x, t.y ?? 0);
        ctx.stroke();
      }
      ctx.globalAlpha = 1;

      // Nodes.
      for (const node of this.nodes) {
        if (typeof node.x !== 'number' || typeof node.y !== 'number') continue;
        ctx.fillStyle = '#1F2937';
        ctx.strokeStyle = '#F59E0B';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(node.x, node.y, NODE_RADIUS, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();

        ctx.fillStyle = '#F9FAFB';
        ctx.font = '11px system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(node.name, node.x, node.y + NODE_RADIUS + 12);
      }
    },

    step(): void {
      this.simulation?.tick();
      this.draw();
    },

    startSimulation(): void {
      if (!this.simulation) return;
      if (this.prefersReducedMotion) {
        this._runToRest();
        return;
      }
      const loop = (): void => {
        this.draw();
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

    handlePointerDown(event: PointerEvent): void {
      if (!this.interactive || !this.canvas) return;
      const rect = this.canvas.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      let nearest: SimNode | null = null;
      let nearestDist = NODE_RADIUS * NODE_RADIUS;
      for (const node of this.nodes) {
        if (typeof node.x !== 'number' || typeof node.y !== 'number') continue;
        const dx = node.x - px;
        const dy = node.y - py;
        const d2 = dx * dx + dy * dy;
        if (d2 < nearestDist) {
          nearestDist = d2;
          nearest = node;
        }
      }
      if (nearest) {
        this._dragging = nearest;
        nearest.fx = nearest.x;
        nearest.fy = nearest.y;
        this.simulation?.alphaTarget(0.3).restart();
      }
    },

    handlePointerMove(event: PointerEvent): void {
      if (!this._dragging || !this.canvas) return;
      const rect = this.canvas.getBoundingClientRect();
      this._dragging.fx = event.clientX - rect.left;
      this._dragging.fy = event.clientY - rect.top;
    },

    handlePointerUp(_event: PointerEvent): void {
      if (!this._dragging) return;
      this._dragging.fx = null;
      this._dragging.fy = null;
      this._dragging = null;
      this.simulation?.alphaTarget(0);
    },

    init(): void {
      this.nodes = reconcileNodes([], this.characters);
      this.links = reconcileLinks(this.nodes, this.relationships);
      // Seed positions near center to avoid the (NaN, NaN) start that
      // causes the first few ticks to look chaotic.
      for (const n of this.nodes) {
        if (typeof n.x !== 'number') n.x = this.width / 2 + (Math.random() - 0.5) * 50;
        if (typeof n.y !== 'number') n.y = this.height / 2 + (Math.random() - 0.5) * 50;
      }

      this.simulation = forceSimulation<SimNode, SimLink>(this.nodes)
        .force(
          'link',
          forceLink<SimNode, SimLink>(this.links)
            .id((d: SimNode) => d.id)
            .distance(80)
            .strength((l) => 0.2 + 0.6 * l.intensity),
        )
        .force('charge', forceManyBody().strength(-150))
        .force('center', forceCenter(this.width / 2, this.height / 2))
        .force('collide', forceCollide(NODE_RADIUS + 4))
        .on('tick', () => {
          this.draw();
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
     * Synchronously tick the simulation until alpha drops below alphaMin
     * (the d3 default settle threshold). Used in reduced-motion mode so we
     * skip animated reveal entirely.
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
    },
  } as CharacterGraphComponent & { _runToRest: () => void };
}
