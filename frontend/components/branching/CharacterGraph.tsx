"use client";

/**
 * CharacterGraph — React port of `web/js/components/CharacterGraph.ts`.
 *
 * Renders character relationship graph using d3-force simulation, drawn as
 * SVG (not Canvas — easier to render inside a shadcn Card and accessible).
 *
 * Performance (R2.3):
 *   - Capped at MAX_NODES (50) visible.
 *   - Simulation runs at most STOP_AFTER_MS (3000ms) then freezes by setting
 *     alphaTarget→0 and stopping.
 *   - No infinite animation loop — uses rAF only while simulation is hot.
 */

import * as React from "react";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type Simulation,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";

export type RelationshipType = "ally" | "enemy" | "rival" | "neutral";

export interface CharacterNode {
  id: string;
  name: string;
  role?: string;
}

export interface CharacterEdge {
  sourceId: string;
  targetId: string;
  type?: RelationshipType;
  intensity?: number;
}

export interface CharacterGraphProps {
  characters: CharacterNode[];
  relationships?: CharacterEdge[];
  width?: number;
  height?: number;
  className?: string;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  name: string;
  role?: string;
}
interface SimLink extends SimulationLinkDatum<SimNode> {
  type: RelationshipType;
  intensity: number;
}

const MAX_NODES = 50;
const STOP_AFTER_MS = 3000;

function edgeColor(type: RelationshipType): string {
  switch (type) {
    case "ally":
      return "var(--success)";
    case "enemy":
      return "var(--destructive)";
    case "rival":
      return "var(--warning)";
    case "neutral":
    default:
      return "var(--muted-foreground)";
  }
}

export default function CharacterGraph({
  characters,
  relationships = [],
  width = 600,
  height = 400,
  className,
}: CharacterGraphProps) {
  // Cap characters early — R2.3.
  const capped = React.useMemo(
    () => characters.slice(0, MAX_NODES),
    [characters]
  );

  const simRef = React.useRef<Simulation<SimNode, SimLink> | null>(null);
  const rafRef = React.useRef<number | null>(null);
  const startRef = React.useRef<number>(0);
  const [, force] = React.useState(0);
  const trigger = React.useCallback(() => force((n) => (n + 1) & 0xff), []);

  // Initialise simulation when input set changes.
  const { nodes, links } = React.useMemo(() => {
    const ns: SimNode[] = capped.map((c, i) => ({
      id: c.id,
      name: c.name,
      role: c.role,
      // Spread along an initial ring so layout is deterministic.
      x: Math.cos((i / Math.max(1, capped.length)) * 2 * Math.PI) * (width / 3) + width / 2,
      y: Math.sin((i / Math.max(1, capped.length)) * 2 * Math.PI) * (height / 3) + height / 2,
    }));
    const idSet = new Set(ns.map((n) => n.id));
    const ls: SimLink[] = relationships
      .filter((r) => idSet.has(r.sourceId) && idSet.has(r.targetId))
      .map((r) => ({
        source: r.sourceId,
        target: r.targetId,
        type: r.type ?? "neutral",
        intensity: typeof r.intensity === "number" ? Math.max(0, Math.min(1, r.intensity)) : 0.5,
      }));
    return { nodes: ns, links: ls };
  }, [capped, relationships, width, height]);

  React.useEffect(() => {
    // Stop any previous sim.
    simRef.current?.stop();
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);

    if (nodes.length === 0) {
      simRef.current = null;
      return;
    }

    const sim = forceSimulation<SimNode>(nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(links)
          .id((n) => n.id)
          .distance((l) => 90 - 30 * (l.intensity ?? 0.5))
          .strength((l) => 0.2 + 0.6 * (l.intensity ?? 0.5))
      )
      .force("charge", forceManyBody().strength(-220))
      .force("center", forceCenter(width / 2, height / 2))
      .force("collide", forceCollide<SimNode>(28))
      .alpha(1)
      .alphaDecay(0.05);

    simRef.current = sim;
    startRef.current = performance.now();

    sim.on("tick", () => {
      // R2.3 — freeze sim after STOP_AFTER_MS regardless of alpha.
      if (performance.now() - startRef.current > STOP_AFTER_MS) {
        sim.alphaTarget(0).stop();
      }
      trigger();
    });

    sim.on("end", () => {
      trigger();
    });

    return () => {
      sim.stop();
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [nodes, links, width, height, trigger]);

  // Build link path data from sim positions (they mutate in place).
  return (
    <div className={className} role="img" aria-label="Đồ thị quan hệ nhân vật">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        style={{ background: "transparent" }}
      >
        <g>
          {links.map((l, i) => {
            const s = l.source as SimNode;
            const t = l.target as SimNode;
            if (!s || !t || typeof s.x !== "number" || typeof t.x !== "number") return null;
            return (
              <line
                key={`l-${i}`}
                x1={s.x}
                y1={s.y!}
                x2={t.x}
                y2={t.y!}
                stroke={edgeColor(l.type)}
                strokeOpacity={0.35 + 0.5 * (l.intensity ?? 0.5)}
                strokeWidth={1 + 1.5 * (l.intensity ?? 0.5)}
              />
            );
          })}
        </g>
        <g>
          {nodes.map((n) => (
            <g key={n.id} transform={`translate(${n.x ?? 0}, ${n.y ?? 0})`}>
              <circle
                r={18}
                fill="var(--card)"
                stroke="var(--accent)"
                strokeWidth={1.5}
              />
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={10}
                fill="var(--foreground)"
                style={{ pointerEvents: "none", userSelect: "none" }}
              >
                {n.name.length > 8 ? n.name.slice(0, 7) + "…" : n.name}
              </text>
            </g>
          ))}
        </g>
      </svg>
      {/* A11y mirror */}
      <ul className="sr-only" role="list">
        {nodes.map((n) => {
          const incident = links
            .filter((l) => (l.source as SimNode).id === n.id || (l.target as SimNode).id === n.id)
            .map((l) => {
              const other = (l.source as SimNode).id === n.id ? (l.target as SimNode) : (l.source as SimNode);
              return `${other.name} (${l.type})`;
            });
          return (
            <li key={n.id}>
              {n.name}: {incident.join(", ") || "không có quan hệ"}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
