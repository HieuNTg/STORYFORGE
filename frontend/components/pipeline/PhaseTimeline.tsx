import * as React from "react";
import { Check, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export type PhaseStatus = "pending" | "active" | "done" | "error";

export interface Phase {
  label: string;
  status: PhaseStatus;
}

/**
 * Optional per-phase substep metadata keyed by phase index. Drives the
 * sub-label beneath the step name and a tiny progress bar on the active step.
 */
export interface PhaseSubInfo {
  subLabel?: string;
  current?: number;
  total?: number;
  doneSummary?: string;
}

export interface PhaseTimelineProps {
  phases: Phase[];
  current?: number;
  /** Optional per-phase substep info keyed by phase index. */
  subInfo?: Record<number, PhaseSubInfo>;
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

export function PhaseTimeline({ phases, current, subInfo, className }: PhaseTimelineProps) {
  return (
    <ol
      className={cn(
        "flex w-full flex-col gap-3 sm:flex-row sm:items-start sm:gap-0",
        className
      )}
      aria-label="Pipeline progress"
    >
      {phases.map((phase, idx) => {
        const isCurrent = current === idx;
        const isFirst = idx === 0;
        const isLast = idx === phases.length - 1;
        const prevStatus: PhaseStatus = idx > 0 ? phases[idx - 1].status : "pending";
        const info = subInfo?.[idx];
        const isActive = phase.status === "active";
        const showLoader = isActive;
        const showProgressBar =
          isActive &&
          typeof info?.current === "number" &&
          typeof info?.total === "number" &&
          info.total > 0;
        const progressPct = showProgressBar
          ? Math.max(0, Math.min(100, Math.round((info!.current! / info!.total!) * 100)))
          : 0;
        const subText = (() => {
          if (phase.status === "done" && info?.doneSummary) return info.doneSummary;
          if (isActive && info?.subLabel) return info.subLabel;
          if (
            isActive &&
            typeof info?.current === "number" &&
            typeof info?.total === "number"
          ) {
            return `${info.current}/${info.total}`;
          }
          return null;
        })();
        return (
          <li
            key={`${phase.label}-${idx}`}
            className="flex items-start gap-3 sm:flex-1 sm:justify-center"
            aria-current={isCurrent ? "step" : undefined}
          >
            <span
              aria-hidden
              className={cn(
                "mt-3 hidden h-px flex-1 sm:block",
                isFirst ? "sm:invisible" : connectorClasses(prevStatus)
              )}
            />
            <div className="flex min-w-0 items-start gap-3 sm:flex-col sm:items-center sm:gap-1.5">
              <span
                className={cn(
                  "relative inline-flex size-6 shrink-0 items-center justify-center rounded-full border text-xs font-medium transition-colors duration-[var(--duration-fast)] ease-[var(--ease-out)]",
                  dotClasses(phase.status)
                )}
                aria-label={`${phase.label} — ${phase.status}`}
              >
                {phase.status === "done" ? (
                  <Check className="size-3.5" aria-hidden />
                ) : phase.status === "error" ? (
                  <AlertCircle className="size-3.5" aria-hidden />
                ) : showLoader ? (
                  <Loader2 className="size-3.5 animate-spin" aria-hidden />
                ) : (
                  <span>{idx + 1}</span>
                )}
                {isActive && (
                  <span
                    aria-hidden
                    className="pointer-events-none absolute inset-0 -z-0 rounded-full bg-accent/30 motion-safe:animate-ping"
                  />
                )}
              </span>
              <div className="flex min-w-0 flex-col gap-0.5 sm:items-center sm:text-center">
                <span
                  className={cn(
                    "text-xs sm:text-center",
                    labelClasses(phase.status, isCurrent)
                  )}
                >
                  {phase.label}
                </span>
                {subText && (
                  <span
                    className={cn(
                      "max-w-[14rem] truncate text-[11px] leading-tight",
                      isActive ? "text-foreground/70" : "text-muted-foreground"
                    )}
                    title={subText}
                  >
                    {subText}
                  </span>
                )}
                {showProgressBar && (
                  <span
                    aria-hidden
                    className="mt-0.5 h-1 w-24 overflow-hidden rounded-full bg-border"
                  >
                    <span
                      className="block h-full bg-accent transition-[width] duration-[var(--duration-fast)] ease-[var(--ease-out)]"
                      style={{ width: `${progressPct}%` }}
                    />
                  </span>
                )}
              </div>
            </div>
            <span
              aria-hidden
              className={cn(
                "mt-3 hidden h-px flex-1 sm:block",
                isLast ? "sm:invisible" : connectorClasses(phase.status)
              )}
            />
          </li>
        );
      })}
    </ol>
  );
}
