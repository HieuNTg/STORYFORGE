"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export interface WordCountCardProps {
  total: number;
  perChapter: number;
  readingTimeMinutes: number;
  className?: string;
}

import { useTranslations, useLocale } from "next-intl";

export function WordCountCard({
  total,
  perChapter,
  readingTimeMinutes,
  className,
}: WordCountCardProps) {
  const t = useTranslations("analytics");
  const locale = useLocale();

  const formatNumber = (n: number) => {
    return Math.round(n).toLocaleString(locale);
  };

  const formatReadingTime = (minutes: number): string => {
    const m = Math.max(0, Math.round(minutes));
    if (m < 60) {
      return t("minutes", { count: m });
    }
    const h = Math.floor(m / 60);
    const rest = m % 60;
    if (rest === 0) {
      return t("hours_only", { hours: h });
    }
    return t("hours_minutes", { hours: h, minutes: rest });
  };

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle>{t("total_words")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pb-4">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold tabular-nums text-foreground">
            {formatNumber(total)}
          </span>
          <span className="text-sm text-muted-foreground">{t("words")}</span>
        </div>

        <dl className="grid grid-cols-2 gap-3 border-t pt-3 text-sm">
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">{t("average_per_chapter")}</dt>
            <dd className="font-medium tabular-nums text-foreground">
              {formatNumber(perChapter)}
            </dd>
          </div>
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">{t("reading_time")}</dt>
            <dd className="font-medium tabular-nums text-foreground">
              {formatReadingTime(readingTimeMinutes)}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
