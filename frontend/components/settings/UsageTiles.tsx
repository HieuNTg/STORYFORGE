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
import { useTranslations } from "next-intl";
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
  const tSettings = useTranslations("settings_panel");
  const tUsage = useTranslations("usage");
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
        {error?.message ?? tSettings("session_empty")}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <StatTile
        label={tUsage("requests")}
        value={formatNumber(data.call_count)}
        hint={tSettings("current_session")}
        icon={<Activity className="size-4" />}
      />
      <StatTile
        label={tUsage("tokens")}
        value={formatNumber(data.total_tokens)}
        hint={tSettings("prompt_out_hint", {
          prompt: formatNumber(data.total_prompt_tokens),
          completion: formatNumber(data.total_completion_tokens),
        })}
        icon={<FileText className="size-4" />}
      />
      <StatTile
        label={tUsage("cost")}
        value={formatCost(data.total_cost_usd)}
        hint={tSettings("model_count", { count: Object.keys(data.by_model).length })}
        icon={<Coins className="size-4" />}
      />
    </div>
  );
}
