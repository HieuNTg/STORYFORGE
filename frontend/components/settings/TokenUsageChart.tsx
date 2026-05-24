"use client";

/**
 * TokenUsageChart — gold-gradient AreaChart of per-model token totals.
 *
 * Backend has no daily timeseries endpoint (audited in Phase 5 Step 1) — we
 * fall back to `/api/usage/session.by_model` which is the only token
 * breakdown that exists today. X-axis = model name; Y-axis = tokens.
 *
 * SSR is OFF — recharts measures DOM on mount and produces a hydration
 * mismatch otherwise.
 */

import * as React from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { Skeleton } from "@/components/ui/skeleton";
import { useUsageSession } from "@/lib/api/usage";

const Chart = dynamic(() => import("./TokenUsageChartInner"), { ssr: false });

export function TokenUsageChart() {
  const t = useTranslations("settings_panel");
  const { data, isLoading, error } = useUsageSession();

  if (isLoading) return <Skeleton className="h-24 w-full" />;

  if (error || !data) {
    return (
      <div className="flex h-24 items-center justify-center rounded-xl border border-dashed border-border bg-card/30 text-xs text-muted-foreground">
        {error?.message ?? t("chart_empty")}
      </div>
    );
  }

  const points = Object.entries(data.by_model)
    .map(([model, v]) => ({ model, tokens: v.tokens, cost: v.cost_usd }))
    .sort((a, b) => b.tokens - a.tokens)
    .slice(0, 10);

  if (points.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center rounded-xl border border-dashed border-border bg-card/30 text-xs text-muted-foreground">
        {t("no_calls")}
      </div>
    );
  }

  return <Chart points={points} />;
}
