"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { QualityGauge } from "@/components/pipeline/QualityGauge";

export interface QualityBreakdownItem {
  label: string;
  /** 0-100 */
  value: number;
}

export interface QualityCardProps {
  /** 0-100 overall score */
  score: number;
  breakdown?: QualityBreakdownItem[];
  className?: string;
}

import { useTranslations } from "next-intl";

export function QualityCard({ score, breakdown, className }: QualityCardProps) {
  const t = useTranslations("analytics");

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle>{t("quality_title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col items-center gap-5 pb-4">
        <QualityGauge value={score} size={140} />
        {breakdown && breakdown.length > 0 ? (
          <ul className="flex w-full flex-col gap-2.5">
            {breakdown.map((item, idx) => {
              const clamped = Math.max(0, Math.min(100, Math.round(item.value)));
              return (
                <li key={`${item.label}-${idx}`} className="flex flex-col gap-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">{item.label}</span>
                    <span className="tabular-nums text-foreground">{clamped}</span>
                  </div>
                  <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                    <div
                      className="h-full bg-accent"
                      style={{ width: `${clamped}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
