"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface PipelineLogLine {
  /** ISO timestamp or short label for the leading `[hh:mm:ss]`. */
  ts?: string;
  /** Optional leading emoji/stage marker. */
  stage?: string;
  /** Body of the line. */
  text: string;
  /** Visual severity — colors only, no layout shift. */
  level?: "info" | "warn" | "error" | "success";
}

export interface PipelineLogTerminalProps {
  lines: PipelineLogLine[];
  className?: string;
  /** Auto-scroll to bottom on new lines. Defaults to true. */
  autoScroll?: boolean;
  /** Max-height for the scroll viewport. Defaults to 280px. */
  maxHeight?: number | string;
}

const LEVEL_COLOR: Record<NonNullable<PipelineLogLine["level"]>, string> = {
  info: "text-foreground/80",
  warn: "text-amber-400",
  error: "text-red-400",
  success: "text-emerald-400",
};

/**
 * PipelineLogTerminal — monospace `>>` prefix log readout for the overlay.
 *
 * Renders a fixed-height scrolling region with autoscroll-to-bottom on
 * new lines. Each line is `>> [hh:mm:ss] {stage} {text}`. Designed for SSE
 * chunk fan-in — push lines on every stream event.
 */
export function PipelineLogTerminal({
  lines,
  className,
  autoScroll = true,
  maxHeight = 280,
}: PipelineLogTerminalProps) {
  const viewportRef = React.useRef<HTMLDivElement | null>(null);
  React.useEffect(() => {
    if (!autoScroll) return;
    const el = viewportRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines, autoScroll]);

  return (
    <div
      ref={viewportRef}
      role="log"
      aria-live="polite"
      aria-relevant="additions"
      className={cn(
        "overflow-y-auto rounded-md border bg-black/40 px-3 py-2",
        "border-[color:var(--reader-rule,var(--border))] font-mono text-xs leading-relaxed",
        className,
      )}
      style={{ maxHeight }}
    >
      {lines.length === 0 ? (
        <p className="text-muted-foreground">{">> đang chờ tín hiệu…"}</p>
      ) : (
        <ul className="space-y-0.5">
          {lines.map((l, i) => (
            <li key={i} className={cn("whitespace-pre-wrap", LEVEL_COLOR[l.level ?? "info"])}>
              <span className="text-muted-foreground">{">> "}</span>
              {l.ts ? (
                <span className="text-muted-foreground">[{l.ts}] </span>
              ) : null}
              {l.stage ? <span className="mr-1">{l.stage}</span> : null}
              <span>{l.text}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
