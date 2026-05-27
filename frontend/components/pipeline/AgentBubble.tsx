import * as React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type AgentStatus = "thinking" | "speaking" | "done" | "error";

export interface AgentBubbleProps {
  name: string;
  role?: string;
  status: AgentStatus;
  message?: string;
  /** Streaming partial text accumulated from SSE `stream` frames. */
  partial?: string;
  turn?: number;
  className?: string;
}

const STATUS_LABEL: Record<AgentStatus, string> = {
  thinking: "Đang nghĩ",
  speaking: "Đang nói",
  done: "Hoàn tất",
  error: "Lỗi",
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function statusDotClass(status: AgentStatus): string {
  switch (status) {
    case "speaking":
    case "thinking":
      return "bg-accent";
    case "done":
      return "bg-muted-foreground";
    case "error":
      return "bg-destructive";
  }
}

function statusBadgeClass(status: AgentStatus): string {
  switch (status) {
    case "speaking":
      return "bg-accent/10 text-accent-foreground border-accent/20";
    case "thinking":
      return "bg-muted text-muted-foreground border-border";
    case "done":
      return "bg-secondary text-secondary-foreground border-transparent";
    case "error":
      return "bg-destructive/10 text-destructive border-destructive/20";
  }
}

function TypingDots() {
  // Three staggered dots; pure CSS animation via `animate-bounce` with delays.
  return (
    <span
      aria-hidden
      className="ml-1 inline-flex items-end gap-0.5 align-baseline"
    >
      <span className="size-1 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:0ms]" />
      <span className="size-1 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:120ms]" />
      <span className="size-1 rounded-full bg-current opacity-70 motion-safe:animate-bounce [animation-delay:240ms]" />
    </span>
  );
}

export function AgentBubble({
  name,
  role,
  status,
  message,
  partial,
  turn,
  className,
}: AgentBubbleProps) {
  const isActive = status === "thinking" || status === "speaking";
  return (
    <Card
      size="sm"
      className={cn(
        "transition-opacity duration-[var(--duration-base)] ease-[var(--ease-out)]",
        status === "thinking" && "opacity-90",
        className
      )}
      data-status={status}
    >
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-center gap-2.5">
          <div
            aria-hidden
            className={cn(
              "flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground",
              isActive && "ring-2 ring-accent/40"
            )}
          >
            {initials(name)}
          </div>
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="flex items-center gap-1.5">
              <span className="truncate text-sm font-medium text-foreground">
                {name}
              </span>
              {typeof turn === "number" ? (
                <span className="text-xs text-muted-foreground">#{turn}</span>
              ) : null}
              {role ? (
                <Badge
                  variant="outline"
                  className="ml-1 h-4 border-border/60 px-1.5 py-0 text-[10px] font-normal text-muted-foreground"
                >
                  {role}
                </Badge>
              ) : null}
            </div>
            {role && !isActive ? (
              <span className="truncate text-xs text-muted-foreground">{role}</span>
            ) : null}
          </div>
          <Badge
            variant="outline"
            className={cn("gap-1.5", statusBadgeClass(status))}
          >
            <span
              aria-hidden
              className={cn(
                "size-1.5 rounded-full",
                statusDotClass(status),
                isActive && "motion-safe:animate-pulse"
              )}
            />
            {STATUS_LABEL[status]}
          </Badge>
        </div>
        {message ? (
          <p className="text-sm leading-relaxed text-muted-foreground">
            {message}
            {status === "thinking" && !partial ? <TypingDots /> : null}
          </p>
        ) : status === "thinking" && !partial ? (
          <p className="text-sm leading-relaxed text-muted-foreground">
            <TypingDots />
          </p>
        ) : null}
        {partial ? (
          <p
            className="rounded-md bg-muted/40 px-2 py-1.5 font-mono text-xs leading-relaxed text-muted-foreground"
            // Stream buffer is capped upstream (STREAM_BUFFER_CHARS) so this is bounded.
          >
            …{partial}
            {isActive ? (
              <span
                aria-hidden
                className="ml-0.5 inline-block h-3 w-1.5 translate-y-0.5 bg-accent motion-safe:animate-pulse"
              />
            ) : null}
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
