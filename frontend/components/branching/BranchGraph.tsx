"use client";

import * as React from "react";
import {
  ReactFlow,
  Background,
  MiniMap,
  Controls,
  type Node,
  type Edge,
  type NodeProps,
  type NodeTypes,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { cn } from "@/lib/utils";
import { layoutBranches } from "@/lib/graph/dagre-layout";
import {
  BranchNodeCard,
  type BranchNodeCardStatus,
} from "./BranchNodeCard";

export type BranchNodeStatus = BranchNodeCardStatus;

export interface BranchGraphNode {
  id: string;
  /** Parent id — used by dagre to compute layout. */
  parentId?: string | null;
  /** Optional explicit position override (skips dagre for this node). */
  position?: { x: number; y: number };
  data: {
    label: string;
    summary?: string;
    status: BranchNodeStatus;
    childCount?: number;
    word_count?: number;
  };
}

export interface BranchGraphEdge {
  id: string;
  source: string;
  target: string;
}

export interface BranchGraphProps {
  nodes: BranchGraphNode[];
  edges: BranchGraphEdge[];
  onNodeClick: (id: string) => void;
  onReadNode?: (id: string) => void;
  selectedId?: string;
  className?: string;
  /** Height of the flow canvas. Defaults to 480px. */
  height?: number | string;
}

const NODE_W = 288;
const NODE_H = 152;

interface ChapterNodeData {
  label: string;
  summary?: string;
  status: BranchNodeStatus;
  childCount?: number;
  onRead?: () => void;
  onBranch?: () => void;
}

function ChapterNode({ data, selected }: NodeProps) {
  const d = data as unknown as ChapterNodeData;
  return (
    <div className="relative">
      <Handle
        type="target"
        position={Position.Left}
        className="!size-1.5 !border !border-border !bg-background"
      />
      <BranchNodeCard
        title={d.label}
        summary={d.summary}
        status={d.status}
        childCount={d.childCount}
        selected={selected}
        onRead={d.onRead}
        onBranch={d.onBranch}
      />
      <Handle
        type="source"
        position={Position.Right}
        className="!size-1.5 !border !border-border !bg-background"
      />
    </div>
  );
}

const nodeTypes: NodeTypes = { chapter: ChapterNode };

function useThemeColors() {
  const [colors, setColors] = React.useState({
    accent: "#a78bfa",
    muted: "#64748b",
    border: "#334155",
    card: "#0f172a",
  });
  React.useEffect(() => {
    const read = () => {
      const cs = getComputedStyle(document.documentElement);
      const pick = (v: string, fb: string) => {
        const raw = cs.getPropertyValue(v).trim();
        return raw || fb;
      };
      setColors({
        accent: pick("--accent", "#a78bfa"),
        muted: pick("--muted-foreground", "#64748b"),
        border: pick("--border", "#334155"),
        card: pick("--card", "#0f172a"),
      });
    };
    read();
    const obs = new MutationObserver(read);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "style"],
    });
    return () => obs.disconnect();
  }, []);
  return colors;
}

export function BranchGraph({
  nodes,
  edges,
  onNodeClick,
  onReadNode,
  selectedId,
  className,
  height = 480,
}: BranchGraphProps) {
  const themeColors = useThemeColors();
  // Structural key — only rerun dagre when graph topology changes, not on
  // every parent re-render that hands us a new array identity.
  const layoutKey = React.useMemo(
    () =>
      nodes
        .map((n) => `${n.id}:${n.parentId ?? ""}:${n.position ? `${n.position.x},${n.position.y}` : "_"}`)
        .join("|"),
    [nodes],
  );
  const positions = React.useMemo(() => {
    const needLayout = nodes.filter((n) => !n.position);
    const laid = layoutBranches(
      needLayout.map((n) => ({ id: n.id, parentId: n.parentId ?? null })),
    );
    const map = new Map<string, { x: number; y: number }>();
    for (const n of nodes) {
      if (n.position) map.set(n.id, n.position);
    }
    for (const l of laid) map.set(l.id, { x: l.x, y: l.y });
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layoutKey]);

  const flowNodes = React.useMemo<Node[]>(
    () =>
      nodes.map((n) => {
        const pos = positions.get(n.id) ?? { x: 0, y: 0 };
        return {
          id: n.id,
          type: "chapter",
          position: pos,
          width: NODE_W,
          height: NODE_H,
          data: {
            label: n.data.label,
            summary: n.data.summary,
            status: n.data.status,
            childCount: n.data.childCount,
            onRead: onReadNode ? () => onReadNode(n.id) : undefined,
            onBranch: () => onNodeClick(n.id),
          } satisfies ChapterNodeData,
          selected: n.id === selectedId,
          draggable: false,
        };
      }),
    [nodes, positions, selectedId, onNodeClick, onReadNode],
  );

  const flowEdges = React.useMemo<Edge[]>(
    () =>
      edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: "smoothstep",
        style: { stroke: "var(--border)", strokeWidth: 1.5 },
      })),
    [edges],
  );

  return (
    <div
      className={cn(
        "branch-graph relative w-full overflow-hidden rounded-xl border bg-card",
        className,
      )}
      style={{ height }}
    >
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodeClick={(_e, node) => onNodeClick(node.id)}
        fitView
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        panOnScroll
        zoomOnPinch
      >
        <Background variant={"dots" as never} gap={20} size={1} color="var(--border)" />
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          maskColor="rgba(0,0,0,0.35)"
          nodeColor={(n) => {
            const s = (n.data as unknown as ChapterNodeData | undefined)?.status;
            if (s === "current" || s === "choice") return themeColors.accent;
            if (s === "visited") return themeColors.muted;
            return themeColors.border;
          }}
          nodeStrokeColor={themeColors.border}
          style={{
            backgroundColor: themeColors.card,
            border: `1px solid ${themeColors.border}`,
            borderRadius: 8,
          }}
        />
        <Controls
          position="bottom-left"
          showInteractive={false}
          style={{
            backgroundColor: "var(--card)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            overflow: "hidden",
          }}
        />
      </ReactFlow>
    </div>
  );
}
