"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BookOpen, GitBranch } from "lucide-react";

export type BranchNodeCardStatus = "visited" | "current" | "pending" | "choice";

export interface BranchNodeCardProps {
  title: string;
  summary?: string;
  status: BranchNodeCardStatus;
  /** Number of direct children, shown as gold pill in the corner. */
  childCount?: number;
  /** Selected by URL/store — adds an accent ring. */
  selected?: boolean;
  /** Reader action: jump into the chapter at this node. */
  onRead?: () => void;
  /** Branch action: open this node in the branch view (goto). */
  onBranch?: () => void;
  className?: string;
}

const STATUS_LABEL: Record<BranchNodeCardStatus, string> = {
  visited: "Đã đọc",
  current: "Hiện tại",
  pending: "Chưa đọc",
  choice: "Lựa chọn",
};

/**
 * BranchNodeCard — 288px wide card used inside xyflow nodes.
 *
 * Phase 4 contract:
 *   - Width: 288px (matches DEFAULT_NODE_W in dagre-layout)
 *   - Serif title (line-clamp-2), serif muted summary (line-clamp-3)
 *   - Status badge + child-count pill (gold) in the header row
 *   - Reader / Branch action buttons in the footer
 */
export function BranchNodeCard({
  title,
  summary,
  status,
  childCount,
  selected,
  onRead,
  onBranch,
  className,
}: BranchNodeCardProps) {
  const isCurrent = status === "current";
  return (
    <div
      data-status={status}
      className={cn(
        "flex w-72 flex-col gap-2 rounded-xl border bg-card px-3 py-2.5 text-card-foreground",
        "border-[color:var(--reader-rule,var(--border))]",
        "transition-colors duration-[var(--duration-fast)] ease-[var(--ease-out)]",
        isCurrent && "border-accent ring-1 ring-accent",
        status === "pending" && "border-dashed text-muted-foreground",
        selected && !isCurrent && "ring-1 ring-accent/60",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <Badge
          variant={isCurrent ? "default" : status === "choice" ? "outline" : "secondary"}
          className="shrink-0"
        >
          {STATUS_LABEL[status]}
        </Badge>
        {typeof childCount === "number" && childCount > 0 ? (
          <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-medium text-accent">
            {childCount} nhánh
          </span>
        ) : null}
      </div>

      <p className="line-clamp-2 font-serif text-sm font-medium leading-snug text-foreground">
        {title}
      </p>
      {summary ? (
        <p className="line-clamp-3 font-serif text-xs leading-relaxed text-muted-foreground">
          {summary}
        </p>
      ) : null}

      {(onRead || onBranch) && (
        <div className="mt-1 flex items-center gap-1.5">
          {onRead ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 flex-1 gap-1 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                onRead();
              }}
            >
              <BookOpen className="size-3" aria-hidden />
              Đọc
            </Button>
          ) : null}
          {onBranch ? (
            <Button
              type="button"
              size="sm"
              variant="outline"
              className="h-7 flex-1 gap-1 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                onBranch();
              }}
            >
              <GitBranch className="size-3" aria-hidden />
              Nhánh
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}
