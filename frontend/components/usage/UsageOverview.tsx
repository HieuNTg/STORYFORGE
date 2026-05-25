"use client";

/**
 * UsageOverview — top stat row for /usage. Reuses StatCard look from Account.
 */

import * as React from "react";
import { Coins, Hash, Sigma, Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { LucideIcon } from "lucide-react";

export interface UsageOverviewProps {
  totalTokens: number;
  promptTokens: number;
  completionTokens: number;
  totalCostUsd: number;
  callCount: number;
}

import { useTranslations, useLocale } from "next-intl";

function formatCost(usd: number): string {
  if (!Number.isFinite(usd)) return "$0";
  if (usd === 0) return "$0";
  if (usd < 0.01) return "$" + usd.toFixed(4);
  return "$" + usd.toFixed(2);
}

interface StatProps {
  icon: LucideIcon;
  label: string;
  value: string;
  description?: string;
  /** Token name e.g. "--chart-1". Tints the leading icon for color recall. */
  accent?: string;
}

function Stat({ icon: Icon, label, value, description, accent }: StatProps) {
  return (
    <Card size="sm" className="motion-lift">
      <CardHeader className="flex flex-row items-center gap-2.5 pb-1">
        <span
          aria-hidden="true"
          className="flex size-7 items-center justify-center rounded-md"
          style={
            accent
              ? {
                  backgroundColor: `color-mix(in oklch, var(${accent}) 14%, transparent)`,
                  color: `var(${accent})`,
                }
              : undefined
          }
        >
          <Icon className="size-4" />
        </span>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tabular-nums text-foreground">
          {value}
        </p>
        {description ? (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function UsageOverview({
  totalTokens,
  promptTokens,
  completionTokens,
  totalCostUsd,
  callCount,
}: UsageOverviewProps) {
  const t = useTranslations("usage");
  const locale = useLocale();
  const N = React.useMemo(() => new Intl.NumberFormat(locale), [locale]);

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Stat
        icon={Sigma}
        label={t("total_tokens")}
        value={N.format(totalTokens)}
        description={t("prompt_completion_desc", {
          prompt: N.format(promptTokens),
          completion: N.format(completionTokens),
        })}
        accent="--chart-1"
      />
      <Stat
        icon={Coins}
        label={t("estimated_cost")}
        value={formatCost(totalCostUsd)}
        description={t("cost_desc")}
        accent="--chart-2"
      />
      <Stat
        icon={Activity}
        label={t("call_count")}
        value={N.format(callCount)}
        description={t("call_count_desc")}
        accent="--chart-3"
      />
      <Stat
        icon={Hash}
        label={t("avg_per_call")}
        value={
          callCount > 0 ? N.format(Math.round(totalTokens / callCount)) : "—"
        }
        description={t("tokens_per_call")}
        accent="--chart-5"
      />
    </div>
  );
}
