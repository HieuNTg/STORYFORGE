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
  ResponsiveContainer,
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
    <div style={{ width: "100%", height: size }} aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="75%">
          <PolarGrid stroke="hsl(var(--border))" strokeOpacity={0.4} />
          <PolarAngleAxis
            dataKey="axis"
            tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 11 }}
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
            stroke="hsl(var(--primary))"
            fill="hsl(var(--primary))"
            fillOpacity={0.35}
            isAnimationActive={false}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
