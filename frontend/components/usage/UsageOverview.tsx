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

const N = new Intl.NumberFormat("vi-VN");

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
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <Stat
        icon={Sigma}
        label="Tổng token"
        value={N.format(totalTokens)}
        description={`Prompt ${N.format(promptTokens)} · Hoàn thành ${N.format(completionTokens)}`}
        accent="--chart-1"
      />
      <Stat
        icon={Coins}
        label="Chi phí ước tính"
        value={formatCost(totalCostUsd)}
        description="USD theo bảng giá nhà cung cấp"
        accent="--chart-2"
      />
      <Stat
        icon={Activity}
        label="Số lệnh gọi"
        value={N.format(callCount)}
        description="Tổng số lượt gọi LLM trong phiên"
        accent="--chart-3"
      />
      <Stat
        icon={Hash}
        label="Trung bình / lệnh"
        value={
          callCount > 0 ? N.format(Math.round(totalTokens / callCount)) : "—"
        }
        description="Token mỗi lệnh gọi"
        accent="--chart-5"
      />
    </div>
  );
}
