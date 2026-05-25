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

import { useTranslations, useLocale } from "next-intl";

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

function formatTs(ts: number, locale: string): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString(locale, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function EventTimeline({ events, className }: EventTimelineProps) {
  const t = useTranslations("analytics");
  const locale = useLocale();

  if (events.length === 0) {
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        {t("no_events")}
      </p>
    );
  }

  const getEventLabel = (type: TimelineEventType) => {
    switch (type) {
      case "simulation": return t("event_simulation");
      case "enhancement": return t("event_enhancement");
      case "gate": return t("event_gate");
      case "rewrite": return t("event_rewrite");
      default: return type;
    }
  };

  return (
    <ol
      className={cn("relative flex flex-col gap-3", className)}
      aria-label={t("event_timeline")}
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
                {formatTs(evt.ts, locale)}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{getEventLabel(evt.type)}</span>
              {typeof evt.chapter === "number" ? (
                <>
                  <span aria-hidden>·</span>
                  <span className="tabular-nums">{t("chapter_name", { num: evt.chapter })}</span>
                </>
              ) : null}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}
