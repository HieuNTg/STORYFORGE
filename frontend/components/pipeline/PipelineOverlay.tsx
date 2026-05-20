"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Progress } from "@/components/ui/progress";
import {
  PipelineLogTerminal,
  type PipelineLogLine,
} from "./PipelineLogTerminal";

export type PipelineStageId =
  | "analyze"
  | "generate"
  | "stream"
  | "finalize";

export interface PipelineStage {
  id: PipelineStageId;
  label: string;
  emoji: string;
}

export const DEFAULT_PIPELINE_STAGES: ReadonlyArray<PipelineStage> = [
  { id: "analyze", label: "Phân tích", emoji: "🔍" },
  { id: "generate", label: "Sinh nội dung", emoji: "✍️" },
  { id: "stream", label: "Truyền dòng", emoji: "📡" },
  { id: "finalize", label: "Hoàn thiện", emoji: "✓" },
];

export interface PipelineOverlayProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 0..stages.length-1 — currently active stage. */
  currentStageIdx: number;
  /** 0..100 progress within the current stage. */
  stageProgress?: number;
  /** Log buffer (newest at the bottom). */
  log: PipelineLogLine[];
  /** Optional stage override. Defaults to DEFAULT_PIPELINE_STAGES. */
  stages?: ReadonlyArray<PipelineStage>;
  /** Optional title — defaults to "Đang sinh nội dung". */
  title?: string;
  /** Optional sub-title under the main title. */
  description?: string;
}

/**
 * PipelineOverlay — right-side Sheet (480px) showing live pipeline progress.
 *
 * Layout:
 *   ┌────────────────────────────┐
 *   │ Title                     │
 *   │ Description               │
 *   ├────────────────────────────┤
 *   │ [stage chips • 4 stages]  │
 *   │ [progress bar]            │
 *   ├────────────────────────────┤
 *   │ Terminal log (mono `>>`)  │
 *   └────────────────────────────┘
 *
 * Stage progression is driven by `currentStageIdx`. Caller maps SSE
 * `chunk|complete|error` events → stage transitions + log lines.
 */
export function PipelineOverlay({
  open,
  onOpenChange,
  currentStageIdx,
  stageProgress = 0,
  log,
  stages = DEFAULT_PIPELINE_STAGES,
  title = "Đang sinh nội dung",
  description,
}: PipelineOverlayProps) {
  const cur = Math.max(0, Math.min(stages.length - 1, currentStageIdx));
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-4 sm:!max-w-[480px] sm:!w-[480px]"
      >
        <SheetHeader className="pr-10">
          <SheetTitle className="font-serif text-lg">{title}</SheetTitle>
          {description ? (
            <SheetDescription>{description}</SheetDescription>
          ) : null}
        </SheetHeader>

        <div className="space-y-3 px-4">
          <ol className="grid grid-cols-4 gap-2">
            {stages.map((s, idx) => {
              const done = idx < cur;
              const active = idx === cur;
              return (
                <li
                  key={s.id}
                  className={cn(
                    "flex flex-col items-center gap-1 rounded-md border px-2 py-2 text-center text-[11px]",
                    "border-[color:var(--reader-rule,var(--border))]",
                    done && "border-emerald-400/40 text-emerald-400",
                    active && "border-accent text-accent",
                    !done && !active && "text-muted-foreground",
                  )}
                  aria-current={active ? "step" : undefined}
                >
                  <span className="text-base leading-none">{s.emoji}</span>
                  <span className="leading-tight">{s.label}</span>
                </li>
              );
            })}
          </ol>
          <Progress
            value={Math.max(0, Math.min(100, stageProgress))}
            className="h-1.5"
          />
        </div>

        <div className="flex-1 overflow-hidden px-4 pb-4">
          <PipelineLogTerminal lines={log} maxHeight="100%" className="h-full" />
        </div>
      </SheetContent>
    </Sheet>
  );
}
