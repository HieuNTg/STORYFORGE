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

function formatNumber(n: number): string {
  return Math.round(n).toLocaleString("vi-VN");
}

function formatReadingTime(minutes: number): string {
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m} phút`;
  const h = Math.floor(m / 60);
  const rest = m % 60;
  return rest === 0 ? `${h} giờ` : `${h} giờ ${rest} phút`;
}

export function WordCountCard({
  total,
  perChapter,
  readingTimeMinutes,
  className,
}: WordCountCardProps) {
  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle>Tổng số từ</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 pb-4">
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold tabular-nums text-foreground">
            {formatNumber(total)}
          </span>
          <span className="text-sm text-muted-foreground">từ</span>
        </div>

        <dl className="grid grid-cols-2 gap-3 border-t pt-3 text-sm">
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">Trung bình / chương</dt>
            <dd className="font-medium tabular-nums text-foreground">
              {formatNumber(perChapter)}
            </dd>
          </div>
          <div className="flex flex-col gap-0.5">
            <dt className="text-xs text-muted-foreground">Thời gian đọc</dt>
            <dd className="font-medium tabular-nums text-foreground">
              {formatReadingTime(readingTimeMinutes)}
            </dd>
          </div>
        </dl>
      </CardContent>
    </Card>
  );
}
