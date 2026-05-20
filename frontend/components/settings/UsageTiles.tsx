"use client";

/**
 * UsageTiles — 3-tile usage snapshot from session usage tracker.
 *
 * Backend exposes `/api/usage/session` only (no daily timeseries endpoint).
 * "Today" therefore = this session; the 7d/30d hints stay blank with a
 * caveat note rather than fake data.
 */

import * as React from "react";
import { Activity, Coins, FileText } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { StatTile } from "./StatTile";
import { useUsageSession } from "@/lib/api/usage";

function formatNumber(n: number): string {
  return new Intl.NumberFormat("vi-VN").format(n);
}

function formatCost(n: number): string {
  return `$${n.toFixed(4)}`;
}

export function UsageTiles() {
  const { data, isLoading, error } = useUsageSession();

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="rounded-xl border border-dashed border-border bg-card/30 p-4 text-xs text-muted-foreground">
        {error?.message ?? "Chưa có dữ liệu sử dụng cho phiên này."}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <StatTile
        label="Yêu cầu"
        value={formatNumber(data.call_count)}
        hint="Phiên hiện tại"
        icon={<Activity className="size-4" />}
      />
      <StatTile
        label="Tokens"
        value={formatNumber(data.total_tokens)}
        hint={`Prompt ${formatNumber(data.total_prompt_tokens)} · Out ${formatNumber(data.total_completion_tokens)}`}
        icon={<FileText className="size-4" />}
      />
      <StatTile
        label="Chi phí USD"
        value={formatCost(data.total_cost_usd)}
        hint={`${Object.keys(data.by_model).length} model${Object.keys(data.by_model).length === 1 ? "" : "s"}`}
        icon={<Coins className="size-4" />}
      />
    </div>
  );
}
