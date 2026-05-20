"use client";

import * as React from "react";
import { ArrowDown, ArrowUp, Minus, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent } from "@/components/ui/card";

export type StatTrendDirection = "up" | "down" | "flat";

export interface StatTrend {
  direction: StatTrendDirection;
  label: string;
}

export interface StatCardProps {
  icon?: LucideIcon;
  label: string;
  value: string | number;
  description?: string;
  trend?: StatTrend;
  className?: string;
}

const trendIcon: Record<StatTrendDirection, LucideIcon> = {
  up: ArrowUp,
  down: ArrowDown,
  flat: Minus,
};

/**
 * Tone uses muted variants for direction — accent for `up`, muted for
 * `flat`/`down`. We deliberately avoid red/green semantics here.
 */
const trendToneClass: Record<StatTrendDirection, string> = {
  up: "bg-accent/10 text-accent",
  down: "bg-muted text-muted-foreground",
  flat: "bg-muted text-muted-foreground",
};

export function StatCard({
  icon: Icon,
  label,
  value,
  description,
  trend,
  className,
}: StatCardProps) {
  const TrendIcon = trend ? trendIcon[trend.direction] : null;

  return (
    <Card className={cn(className)}>
      <CardContent className="flex flex-col gap-2 py-2">
        <div className="flex items-start justify-between gap-3">
          {Icon ? (
            <span
              aria-hidden
              className="flex size-8 items-center justify-center rounded-lg bg-muted text-foreground/80"
            >
              <Icon className="size-4" />
            </span>
          ) : (
            <span aria-hidden />
          )}
          {trend && TrendIcon ? (
            <span
              className={cn(
                "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                trendToneClass[trend.direction],
              )}
            >
              <TrendIcon className="size-3" aria-hidden />
              {trend.label}
            </span>
          ) : null}
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-2xl font-medium tabular-nums leading-none text-foreground">
            {value}
          </span>
          <span className="text-sm text-muted-foreground">{label}</span>
          {description ? (
            <span className="text-xs text-muted-foreground/80">
              {description}
            </span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
