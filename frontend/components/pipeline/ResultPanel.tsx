"use client";

import * as React from "react";
import { BookOpen, FileText } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
  CardAction,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { EmptyState } from "@/components/common/EmptyState";
import { cn } from "@/lib/utils";

export interface ResultChapter {
  id: string;
  title: string;
  word_count: number;
}

export interface ResultStory {
  id: string;
  title: string;
  chapters: ResultChapter[];
}

/** Live partial chapter shown before the `done` frame ships the final story. */
export interface PartialResultChapter {
  id: string;
  number: number | null;
  title: string;
  /** Epoch ms appended; drives "vừa xong" caption. */
  appendedAt?: number;
}

export interface ResultPanelProps {
  story?: ResultStory;
  /**
   * Partial chapters sniffed from SSE logs while generation is in-flight.
   * Used to populate the panel BEFORE the final `done` frame arrives so the
   * card stops feeling inert during multi-minute generations.
   */
  partialChapters?: PartialResultChapter[];
  /** Optional total chapter target for the "X / N" progress line. */
  totalChapters?: number;
  onOpenReader?: () => void;
  /**
   * Extra header content rendered next to / instead of the "Đọc truyện"
   * button. Used by Khai sinh to surface a "Lưu vào thư viện" CTA without
   * binding this panel to the library store.
   */
  headerAction?: React.ReactNode;
  className?: string;
}

function formatNumber(n: number): string {
  return new Intl.NumberFormat("vi-VN").format(n);
}

export function ResultPanel({
  story,
  partialChapters,
  totalChapters,
  onOpenReader,
  headerAction,
  className,
}: ResultPanelProps) {
  if (!story) {
    const partials = (partialChapters ?? [])
      .slice()
      .sort((a, b) => (a.number ?? 0) - (b.number ?? 0));
    if (partials.length === 0) {
      return (
        <Card className={className}>
          <CardContent>
            <EmptyState
              icon={FileText}
              title="Chưa có kết quả"
              description="Kết quả sẽ hiển thị tại đây sau khi quá trình sáng tác hoàn tất."
            />
          </CardContent>
        </Card>
      );
    }
    const total = totalChapters ?? null;
    return (
      <Card className={cn(className)}>
        <CardHeader className="border-b">
          <CardTitle className="text-lg">Đang sáng tác…</CardTitle>
          <CardDescription>
            {total
              ? `${formatNumber(partials.length)} / ${formatNumber(total)} chương đã viết xong`
              : `${formatNumber(partials.length)} chương đã viết xong`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="max-h-[420px] pr-2">
            <ul className="flex flex-col">
              {partials.map((ch, idx) => (
                <React.Fragment key={ch.id}>
                  {idx > 0 ? <Separator /> : null}
                  <li className="flex items-center justify-between gap-3 py-2.5">
                    <div className="flex min-w-0 items-baseline gap-2">
                      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                        {ch.number != null
                          ? String(ch.number).padStart(2, "0")
                          : String(idx + 1).padStart(2, "0")}
                      </span>
                      <span className="truncate text-sm text-foreground">{ch.title}</span>
                    </div>
                    <Badge
                      variant="outline"
                      className="border-accent/40 text-[10px] text-accent-foreground"
                    >
                      vừa xong
                    </Badge>
                  </li>
                </React.Fragment>
              ))}
            </ul>
          </ScrollArea>
        </CardContent>
      </Card>
    );
  }

  const totalWords = story.chapters.reduce((s, c) => s + (c.word_count || 0), 0);

  return (
    <Card className={cn(className)}>
      <CardHeader className="border-b">
        <CardTitle className="text-lg">{story.title}</CardTitle>
        <CardDescription>
          {formatNumber(story.chapters.length)} chương · {formatNumber(totalWords)} từ
        </CardDescription>
        {onOpenReader || headerAction ? (
          <CardAction>
            <div className="flex flex-wrap items-center gap-2">
              {headerAction}
              {onOpenReader ? (
                <Button onClick={onOpenReader}>
                  <BookOpen aria-hidden />
                  Đọc truyện
                </Button>
              ) : null}
            </div>
          </CardAction>
        ) : null}
      </CardHeader>
      <CardContent>
        {story.chapters.length === 0 ? (
          <p className="text-sm text-muted-foreground">Chưa có chương nào.</p>
        ) : (
          <ScrollArea className="max-h-[420px] pr-2">
            <ul className="flex flex-col">
              {story.chapters.map((ch, idx) => (
                <React.Fragment key={ch.id}>
                  {idx > 0 ? <Separator /> : null}
                  <li className="flex items-center justify-between gap-3 py-2.5">
                    <div className="flex min-w-0 items-baseline gap-2">
                      <span className="shrink-0 text-xs tabular-nums text-muted-foreground">
                        {String(idx + 1).padStart(2, "0")}
                      </span>
                      <span className="truncate text-sm text-foreground">
                        {ch.title}
                      </span>
                    </div>
                    <Badge variant="secondary" className="tabular-nums">
                      {formatNumber(ch.word_count)} từ
                    </Badge>
                  </li>
                </React.Fragment>
              ))}
            </ul>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
}
