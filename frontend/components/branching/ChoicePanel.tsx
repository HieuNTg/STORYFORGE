"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

export interface ChoiceOption {
  id: string;
  label: string;
  preview?: string;
}

export interface ChoicePanelProps {
  /** Current chapter content. Hidden when streaming text takes over. */
  currentChapterText?: string;
  choices: ChoiceOption[];
  onChoose: (id: string) => void;
  isLoading?: boolean;
  isStreaming?: boolean;
  streamingText?: string;
  className?: string;
}

export function ChoicePanel({
  currentChapterText,
  choices,
  onChoose,
  isLoading = false,
  isStreaming = false,
  streamingText,
  className,
}: ChoicePanelProps) {
  // Pick the body to display: streaming text wins while active, otherwise the
  // current chapter. Streaming text appears live and is replaced on completion
  // by the next chapter (which the parent fetches and passes via currentChapterText).
  const bodyText = isStreaming ? streamingText ?? "" : currentChapterText ?? "";
  const hasChoices = choices.length > 0;

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {/* Current/streaming body */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Đoạn hiện tại</CardTitle>
            {isStreaming ? (
              <Badge variant="outline" className="text-accent">
                Đang tạo nội dung...
              </Badge>
            ) : null}
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="max-h-[420px] pr-2">
            {bodyText ? (
              <div
                className="flex flex-col gap-3 text-sm leading-relaxed text-foreground"
                // While streaming, announce new prose progressively for SR users
                // (WCAG 4.1.3 Status Messages). When static, no live region.
                aria-live={isStreaming ? "polite" : undefined}
                aria-busy={isStreaming ? true : undefined}
              >
                {bodyText
                  .split(/\n{2,}|\n+/)
                  .filter((p) => p.trim().length > 0)
                  .map((para, idx) => (
                    <p key={idx} className="m-0">
                      {para}
                    </p>
                  ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Chưa có nội dung.
              </p>
            )}
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Choices */}
      <Card>
        <CardHeader>
          <CardTitle>Lựa chọn tiếp theo</CardTitle>
        </CardHeader>
        <CardContent className="pb-4">
          {!hasChoices ? (
            <p className="text-sm text-muted-foreground">Chưa có lựa chọn.</p>
          ) : (
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {choices.map((c) => (
                <Button
                  key={c.id}
                  type="button"
                  variant="outline"
                  size="lg"
                  disabled={isLoading || isStreaming}
                  onClick={() => onChoose(c.id)}
                  className="h-auto min-h-[3.5rem] flex-col items-start justify-center gap-1 px-3.5 py-3 text-left whitespace-normal"
                >
                  <span className="text-sm font-medium text-foreground">
                    {c.label}
                  </span>
                  {c.preview ? (
                    <span className="line-clamp-2 text-xs font-normal text-muted-foreground">
                      {c.preview}
                    </span>
                  ) : null}
                </Button>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
