"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type TimelineEventType = "simulation" | "enhancement" | "gate" | "rewrite";

export interface TimelineEvent {
  ts: number;
  type: TimelineEventType;
  label: string;
  chapter?: number;
}

export interface EventTimelineProps {
  events: TimelineEvent[];
  className?: string;
}

const EVENT_TYPE_LABEL: Record<TimelineEventType, string> = {
  simulation: "Mô phỏng",
  enhancement: "Cải thiện",
  gate: "Kiểm tra",
  rewrite: "Viết lại",
};

/**
 * Map event types to muted-foreground / accent variants only — no new colors.
 * We don't introduce semantic color per type to stay within the single-accent
 * register. Type is conveyed by label, not hue.
 */
function dotClasses(type: TimelineEventType): string {
  switch (type) {
    case "simulation":
    case "enhancement":
      return "border-accent bg-accent";
    case "gate":
      return "border-foreground/40 bg-background";
    case "rewrite":
    default:
      return "border-border bg-muted";
  }
}

function formatTs(ts: number): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function EventTimeline({ events, className }: EventTimelineProps) {
  if (events.length === 0) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        Chưa có sự kiện.
      </p>
    );
  }

  return (
    <ol
      className={cn("relative flex flex-col gap-3", className)}
      aria-label="Dòng thời gian sự kiện"
    >
      {/* Vertical rule, positioned under the dot center (left-2 = 8px + dot 8px). */}
      <span
        aria-hidden
        className="absolute top-1.5 bottom-1.5 left-[7px] w-px bg-border"
      />

      {events.map((evt, idx) => (
        <li key={idx} className="relative flex items-start gap-3 pl-0">
          <span
            aria-hidden
            className={cn(
              "relative z-10 mt-1 size-3.5 shrink-0 rounded-full border-2",
              dotClasses(evt.type)
            )}
          />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-foreground">
                {evt.label}
              </span>
              <span className="text-xs tabular-nums text-muted-foreground">
                {formatTs(evt.ts)}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{EVENT_TYPE_LABEL[evt.type]}</span>
              {typeof evt.chapter === "number" ? (
                <>
                  <span aria-hidden>·</span>
                  <span className="tabular-nums">Chương {evt.chapter}</span>
                </>
              ) : null}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
