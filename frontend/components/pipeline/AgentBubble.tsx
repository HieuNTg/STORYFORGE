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

export function AgentBubble({
  name,
  role,
  status,
  message,
  turn,
  className,
}: AgentBubbleProps) {
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
            className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-medium text-secondary-foreground"
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
            </div>
            {role ? (
              <span className="truncate text-xs text-muted-foreground">{role}</span>
            ) : null}
          </div>
          <Badge
            variant="outline"
            className={cn("gap-1.5", statusBadgeClass(status))}
          >
            <span
              aria-hidden
              className={cn("size-1.5 rounded-full", statusDotClass(status))}
            />
            {STATUS_LABEL[status]}
          </Badge>
        </div>
        {message ? (
          <p className="text-sm leading-relaxed text-muted-foreground">{message}</p>
        ) : null}
      </CardContent>
    </Card>
  );
}
