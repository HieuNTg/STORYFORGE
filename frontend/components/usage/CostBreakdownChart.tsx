"use client";

/**
 * CostBreakdownChart — bar chart used inside Usage page.
 *
 * Loaded via `next/dynamic` from the page so recharts code-splits off the
 * critical bundle (R4.2). Theming follows ChapterChart.
 */

import * as React from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { cn } from "@/lib/utils";

/**
 * Chart palette — references the 5 chart tokens defined in globals.css.
 * Bars rotate through this list by index. WCAG: every hue clears 3:1 against
 * both `--background` (light) and the dark variant.
 */
const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

export interface CostBreakdownDatum {
  label: string;
  tokens: number;
  cost: number;
}

interface TooltipPayloadItem {
  payload?: CostBreakdownDatum;
}

interface TooltipRenderProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}

function ChartTooltip({ active, payload }: TooltipRenderProps) {
  if (!active || !payload || payload.length === 0) return null;
  const d = payload[0].payload;
  if (!d) return null;
  return (
    <div className="rounded-md border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md ring-1 ring-foreground/10">
      <p className="font-medium">{d.label}</p>
      <p className="tabular-nums text-muted-foreground">
        {d.tokens.toLocaleString("vi-VN")} token
      </p>
      <p className="tabular-nums text-muted-foreground">
        ${d.cost.toFixed(4)}
      </p>
    </div>
  );
}

export interface CostBreakdownChartProps {
  data: CostBreakdownDatum[];
  className?: string;
  height?: number;
  dataKey?: "tokens" | "cost";
}

export default function CostBreakdownChart({
  data,
  className,
  height = 260,
  dataKey = "tokens",
}: CostBreakdownChartProps) {
  // Accessible summary — recharts renders bars as SVG paths with no name,
  // so we expose the same info via an aria-label (WCAG 1.1.1, 1.3.1).
  const total = data.reduce((s, d) => s + (d[dataKey] ?? 0), 0);
  const ariaSummary =
    data.length === 0
      ? "Biểu đồ chi phí: không có dữ liệu."
      : `Biểu đồ ${dataKey === "tokens" ? "token" : "chi phí"} theo ${data.length} mô hình. ` +
        data
          .map(
            (d) =>
              `${d.label}: ${d.tokens.toLocaleString("vi-VN")} token, $${d.cost.toFixed(4)}`,
          )
          .join("; ") +
        `. Tổng: ${total.toLocaleString("vi-VN")}.`;
  return (
    <div
      className={cn("w-full", className)}
      style={{ height }}
      role="img"
      aria-label={ariaSummary}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            tickLine={{ stroke: "var(--border)" }}
            axisLine={{ stroke: "var(--border)" }}
            interval={0}
            angle={-20}
            textAnchor="end"
            height={56}
          />
          <YAxis
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            tickLine={{ stroke: "var(--border)" }}
            axisLine={{ stroke: "var(--border)" }}
            width={56}
          />
          <Tooltip
            content={<ChartTooltip />}
            cursor={{ fill: "var(--muted)", opacity: 0.5 }}
          />
          <Bar
            dataKey={dataKey}
            radius={[3, 3, 0, 0]}
            maxBarSize={28}
            isAnimationActive={false}
          >
            {data.map((_, i) => (
              <Cell
                key={`cell-${i}`}
                fill={CHART_COLORS[i % CHART_COLORS.length]}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
