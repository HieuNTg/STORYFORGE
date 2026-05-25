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

import { useTranslations, useLocale } from "next-intl";

interface TooltipPayloadItem {
  payload?: ChapterChartDatum;
  value?: number;
}

interface TooltipRenderProps {
  active?: boolean;
  payload?: TooltipPayloadItem[];
}

interface ChartTooltipProps extends TooltipRenderProps {
  t: any;
  locale: string;
}

function ChartTooltip({ active, payload, t, locale }: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0].payload;
  if (!datum) return null;
  const N = new Intl.NumberFormat(locale);
  return (
    <div className="rounded-md border bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-md ring-1 ring-foreground/10">
      <p className="font-medium">{t("chapter_name", { num: datum.chapter })}</p>
      <p className="tabular-nums text-muted-foreground">
        {N.format(datum.words)} {t("words")}
      </p>
      {typeof datum.quality === "number" ? (
        <p className="tabular-nums text-muted-foreground">
          {t("quality", { val: Math.round(datum.quality) })}
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
  const t = useTranslations("analytics");
  const locale = useLocale();
  const N = React.useMemo(() => new Intl.NumberFormat(locale), [locale]);

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
      ? t("chart_empty")
      : t("chart_summary", {
          count: data.length,
          words: N.format(totalWords),
          avg: avgQuality,
        });

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
              value: t("chapter"),
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
            content={<ChartTooltip t={t} locale={locale} />}
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
