import * as React from "react";
import { Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type PhaseStatus = "pending" | "active" | "done" | "error";

export interface Phase {
  label: string;
  status: PhaseStatus;
}

export interface PhaseTimelineProps {
  phases: Phase[];
  current?: number;
  className?: string;
}

function dotClasses(status: PhaseStatus): string {
  switch (status) {
    case "active":
      return "border-accent bg-accent text-accent-foreground";
    case "done":
      return "border-transparent bg-foreground/80 text-background";
    case "error":
      return "border-destructive bg-destructive/10 text-destructive";
    case "pending":
    default:
      return "border-border bg-background text-muted-foreground";
  }
}

function labelClasses(status: PhaseStatus, isCurrent: boolean): string {
  if (status === "active" || isCurrent) return "text-foreground font-medium";
  if (status === "done") return "text-foreground/80";
  if (status === "error") return "text-destructive";
  return "text-muted-foreground";
}

function connectorClasses(prev: PhaseStatus): string {
  if (prev === "done") return "bg-foreground/40";
  if (prev === "active") return "bg-accent/40";
  if (prev === "error") return "bg-destructive/40";
  return "bg-border";
}

export function PhaseTimeline({ phases, current, className }: PhaseTimelineProps) {
  return (
    <ol
      className={cn(
        "flex w-full flex-col gap-3 sm:flex-row sm:items-center sm:gap-0",
        className
      )}
      aria-label="Pipeline progress"
    >
      {phases.map((phase, idx) => {
        const isCurrent = current === idx;
        const isLast = idx === phases.length - 1;
        return (
          <li
            key={`${phase.label}-${idx}`}
            className="flex items-center gap-3 sm:flex-1"
            aria-current={isCurrent ? "step" : undefined}
          >
            <div className="flex items-center gap-3 sm:flex-col sm:items-center sm:gap-1.5">
              <span
                className={cn(
                  "inline-flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium transition-colors duration-[var(--duration-fast)] ease-[var(--ease-out)]",
                  dotClasses(phase.status)
                )}
                aria-label={`${phase.label} — ${phase.status}`}
              >
                {phase.status === "done" ? (
                  <Check className="size-3.5" aria-hidden />
                ) : phase.status === "error" ? (
                  <AlertCircle className="size-3.5" aria-hidden />
                ) : (
                  <span>{idx + 1}</span>
                )}
              </span>
              <span
                className={cn(
                  "text-xs sm:text-center",
                  labelClasses(phase.status, isCurrent)
                )}
              >
                {phase.label}
              </span>
            </div>
            {!isLast ? (
              <span
                aria-hidden
                className={cn(
                  "hidden h-px flex-1 sm:block",
                  connectorClasses(phase.status)
                )}
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
