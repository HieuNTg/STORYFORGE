"use client";

/**
 * /usage — token + cost dashboard.
 *
 * Data: `GET /api/usage/session` via `useUsageSession`.
 *  - staleTime 60s
 *  - RBAC-gated in production: on 403/network failure we render demo data
 *    with a clear banner saying "Backend endpoint pending / unavailable".
 *
 * Daily breakdown: the backend has no `/api/usage/daily`. The chart uses
 * model-level totals for now and surfaces the same banner when no breakdown
 * is computable. The component contract is stable so wiring real data later
 * is a one-line swap.
 *
 * Code-splitting: the recharts bundle is dynamic-imported (`ssr: false`) so
 * it stays out of the critical path (R4.2).
 */

import * as React from "react";
import dynamic from "next/dynamic";
import { Info } from "lucide-react";
import { PageHero } from "@/components/common/PageHero";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { UsageOverview } from "@/components/usage/UsageOverview";
import { ApiCallsTable } from "@/components/usage/ApiCallsTable";
import type { CostBreakdownDatum } from "@/components/usage/CostBreakdownChart";
import { useUsageSession, type SessionUsageSummary } from "@/lib/api/usage";

import { useTranslations } from "next-intl";

const CostBreakdownChart = dynamic(
  () => import("@/components/usage/CostBreakdownChart"),
  {
    ssr: false,
    loading: () => <Skeleton className="h-64 w-full" />,
  },
);

const DEMO: SessionUsageSummary = {
  call_count: 24,
  total_prompt_tokens: 42_318,
  total_completion_tokens: 28_440,
  total_tokens: 70_758,
  total_cost_usd: 0.4231,
  by_story: {
    "story-1.json": { tokens: 35_000, cost_usd: 0.21 },
    "story-2.json": { tokens: 35_758, cost_usd: 0.2131 },
  },
  by_model: {
    "gpt-4o-mini": { tokens: 50_000, cost_usd: 0.27 },
    "claude-haiku": { tokens: 20_758, cost_usd: 0.1531 },
  },
};

function PendingBanner({ label, message }: { label: string; message: string }) {
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-sm text-foreground"
    >
      <Info className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden="true" />
      <p>
        <span className="font-medium">{label}</span> {message}
      </p>
    </div>
  );
}

export default function UsagePage() {
  const t = useTranslations("usage");
  const usage = useUsageSession();

  const { data, isLoading, error } = usage;
  const showDemo = !!error;
  const eff: SessionUsageSummary | undefined = data ?? (showDemo ? DEMO : undefined);

  if (isLoading && !eff) {
    return (
      <div className="flex flex-col gap-6">
        <PageHero title={t("title")} subtitle={t("loading_subtitle")} />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!eff) {
    return (
      <div className="flex flex-col gap-6">
        <PageHero title={t("title")} />
        <ErrorState
          title={t("load_failed")}
          description={(error as Error | undefined)?.message ?? "Error"}
          onRetry={() => usage.refetch()}
        />
      </div>
    );
  }

  const modelRows = Object.entries(eff.by_model)
    .map(([model, b]) => ({ model, tokens: b.tokens, cost: b.cost_usd }))
    .sort((a, b) => b.cost - a.cost);

  const storyRows = Object.entries(eff.by_story)
    .map(([k, b]) => ({ model: k, tokens: b.tokens, cost: b.cost_usd }))
    .sort((a, b) => b.cost - a.cost);

  const chartData: CostBreakdownDatum[] = modelRows.slice(0, 8).map((r) => ({
    label: r.model,
    tokens: r.tokens,
    cost: r.cost,
  }));

  const empty = eff.call_count === 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title={t("title")}
        subtitle={t("subtitle")}
      />

      {showDemo ? (
        <PendingBanner label={t("backend_pending")} message={t("demo_banner")} />
      ) : null}

      {empty && !showDemo ? (
        <EmptyState variant="usage-empty" />
      ) : (
        <>
          <UsageOverview
            totalTokens={eff.total_tokens}
            promptTokens={eff.total_prompt_tokens}
            completionTokens={eff.total_completion_tokens}
            totalCostUsd={eff.total_cost_usd}
            callCount={eff.call_count}
          />

          <Card>
            <CardHeader>
              <CardTitle>{t("chart_title")}</CardTitle>
            </CardHeader>
            <CardContent>
              {chartData.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("chart_empty")}</p>
              ) : (
                <CostBreakdownChart data={chartData} dataKey="tokens" />
              )}
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <ApiCallsTable rows={modelRows} title={t("table_by_model")} />
            <ApiCallsTable rows={storyRows} title={t("table_by_story")} />
          </div>
        </>
      )}
    </div>
  );
}
