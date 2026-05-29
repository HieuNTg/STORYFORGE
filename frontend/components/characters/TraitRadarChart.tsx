"use client";

/**
 * TraitRadarChart — recharts inner. Imported via next/dynamic with ssr:false
 * by TraitRadar.tsx (recharts has no SSR support).
 */
import * as React from "react";
import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
} from "recharts";
import type { TraitKey, Traits } from "@/types/story";

export interface TraitRadarChartProps {
  traits: Traits;
  axes: readonly TraitKey[];
  axisLabels: Record<TraitKey, string>;
  size?: number;
}

export default function TraitRadarChart({
  traits,
  axes,
  axisLabels,
  size = 220,
}: TraitRadarChartProps) {
  const data = React.useMemo(
    () =>
      axes.map((k) => ({
        axis: axisLabels[k] ?? k,
        value: traits[k] ?? 0,
      })),
    [traits, axes, axisLabels],
  );

  return (
    <div
      style={{
        width: "100%",
        height: size,
        display: "flex",
        justifyContent: "center",
      }}
      aria-hidden
    >
      <RadarChart
        width={size}
        height={size}
        data={data}
        cx="50%"
        cy="50%"
        outerRadius="75%"
      >
          <PolarGrid stroke="var(--border)" strokeOpacity={0.6} />
          <PolarAngleAxis
            dataKey="axis"
            tick={{
              fill: "var(--foreground)",
              fontSize: 12,
              fontWeight: 600,
            }}
          />
          <PolarRadiusAxis
            domain={[0, 100]}
            tick={false}
            axisLine={false}
            stroke="transparent"
          />
          <Radar
            name="traits"
            dataKey="value"
            stroke="var(--primary)"
            strokeWidth={2}
            fill="var(--primary)"
            fillOpacity={0.55}
            dot={{
              r: 3,
              fill: "var(--primary)",
              stroke: "var(--background)",
              strokeWidth: 1,
            }}
            style={{ filter: "drop-shadow(0 0 6px var(--ring))" }}
            isAnimationActive={false}
          />
      </RadarChart>
    </div>
  );
}
