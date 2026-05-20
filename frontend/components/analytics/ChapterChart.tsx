"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface ChapterChartDatum {
  chapter: number;
  words: number;
  quality?: number;
}

export interface ChapterChartProps {
  data: ChapterChartDatum[];
  className?: string;
  height?: number;
}

interface TooltipPayloadItem {
  payload?: ChapterChartDatum;
  value?: number;
}

interface TooltipRenderProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}

function ChartTooltip({ active, payload }: TooltipRenderProps) {
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0].payload;
  if (!datum) return null;
  return (
    <div className="rounded-md border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md ring-1 ring-foreground/10">
      <p className="font-medium">Chương {datum.chapter}</p>
      <p className="tabular-nums text-muted-foreground">
        {datum.words.toLocaleString("vi-VN")} từ
      </p>
      {typeof datum.quality === "number" ? (
        <p className="tabular-nums text-muted-foreground">
          Chất lượng: {Math.round(datum.quality)}
        </p>
      ) : null}
    </div>
  );
}

export function ChapterChart({
  data,
  className,
  height = 280,
}: ChapterChartProps) {
  // Accessible summary for screen readers (WCAG 1.1.1, 1.3.1).
  const totalWords = data.reduce((s, d) => s + (d.words ?? 0), 0);
  const avgQuality =
    data.length > 0
      ? Math.round(
          data.reduce((s, d) => s + (d.quality ?? 0), 0) / data.length,
        )
      : 0;
  const ariaSummary =
    data.length === 0
      ? "Biểu đồ chương: không có dữ liệu."
      : `Biểu đồ ${data.length} chương. Tổng ${totalWords.toLocaleString("vi-VN")} từ. ` +
        (avgQuality > 0 ? `Chất lượng trung bình: ${avgQuality}.` : "");
  return (
    <div
      className={cn("w-full", className)}
      style={{ height }}
      role="img"
      aria-label={ariaSummary}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 8, right: 8, left: 0, bottom: 8 }}
        >
          <CartesianGrid
            stroke="var(--border)"
            strokeDasharray="2 4"
            vertical={false}
          />
          <XAxis
            dataKey="chapter"
            tick={{ fill: "var(--muted-foreground)", fontSize: 11 }}
            tickLine={{ stroke: "var(--border)" }}
            axisLine={{ stroke: "var(--border)" }}
            label={{
              value: "Chương",
              position: "insideBottom",
              offset: -2,
              fill: "var(--muted-foreground)",
              fontSize: 11,
            }}
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
            dataKey="words"
            fill="var(--accent)"
            radius={[3, 3, 0, 0]}
            maxBarSize={28}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
