"use client";

/**
 * dagre-layout — BFS-horizontal layout helper for the branch-graph canvas.
 *
 * Uses @dagrejs/dagre to assign (x,y) to each node based on a DAG of
 * (id, parentId?). Designer brief mandates:
 *   rankdir: 'LR'   — root on the left, children to the right
 *   nodesep: 24     — sibling spacing
 *   ranksep: 80     — generation spacing
 *
 * The graph never has cycles (branch tree), so dagre's layered layout
 * collapses to a clean horizontal tree. Output coordinates are at the
 * node CENTER — @xyflow/react expects top-left, so we subtract w/h/2.
 */

import dagre from "@dagrejs/dagre";

export interface BranchInputNode {
  id: string;
  parentId?: string | null;
  /** Optional explicit node size override; defaults to 288 × 152. */
  width?: number;
  height?: number;
}

export interface LaidOutNode {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

const DEFAULT_NODE_W = 288;
const DEFAULT_NODE_H = 152;

export function layoutBranches(nodes: BranchInputNode[]): LaidOutNode[] {
  if (nodes.length === 0) return [];

  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 80 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of nodes) {
    g.setNode(n.id, {
      width: n.width ?? DEFAULT_NODE_W,
      height: n.height ?? DEFAULT_NODE_H,
    });
  }
  for (const n of nodes) {
    if (n.parentId && nodes.some((p) => p.id === n.parentId)) {
      g.setEdge(n.parentId, n.id);
    }
  }

  dagre.layout(g);

  return nodes.map((n) => {
    const w = n.width ?? DEFAULT_NODE_W;
    const h = n.height ?? DEFAULT_NODE_H;
    const pos = g.node(n.id) as { x?: number; y?: number } | undefined;
    const cx = pos?.x ?? 0;
    const cy = pos?.y ?? 0;
    return { id: n.id, x: cx - w / 2, y: cy - h / 2, width: w, height: h };
  });
}
