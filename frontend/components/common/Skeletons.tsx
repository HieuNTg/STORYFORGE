import * as React from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/* ──────────────────────────────────────────────────────────────────────────
 * Domain-specific skeletons (legacy — kept for existing callers).
 * ────────────────────────────────────────────────────────────────────────── */

export function StoryCardSkeleton({ className }: { className?: string }) {
  return (
    <Card size="sm" className={cn("h-full", className)}>
      <Skeleton className="aspect-[3/4] w-full rounded-none" />
      <CardHeader>
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="mt-1 h-4 w-1/2" />
      </CardHeader>
      <CardContent className="flex items-center gap-2">
        <Skeleton className="h-5 w-12 rounded-full" />
        <Skeleton className="h-3 w-16" />
        <Skeleton className="ml-auto h-3 w-10" />
      </CardContent>
    </Card>
  );
}

export function AgentBubbleSkeleton({ className }: { className?: string }) {
  return (
    <Card size="sm" className={cn(className)}>
      <CardContent className="flex flex-col gap-2">
        <div className="flex items-center gap-2.5">
          <Skeleton className="size-8 rounded-full" />
          <div className="flex flex-1 flex-col gap-1">
            <Skeleton className="h-3.5 w-32" />
            <Skeleton className="h-3 w-20" />
          </div>
          <Skeleton className="h-5 w-20 rounded-full" />
        </div>
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-5/6" />
      </CardContent>
    </Card>
  );
}

export function PhaseTimelineSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "flex w-full flex-col gap-3 sm:flex-row sm:items-center sm:gap-2",
        className
      )}
    >
      {Array.from({ length: 5 }).map((_, i) => (
        <React.Fragment key={i}>
          <div className="flex items-center gap-3 sm:flex-col sm:items-center sm:gap-1.5">
            <Skeleton className="size-6 rounded-full" />
            <Skeleton className="h-3 w-16" />
          </div>
          {i < 4 ? (
            <Skeleton className="hidden h-px flex-1 rounded-none sm:block" />
          ) : null}
        </React.Fragment>
      ))}
    </div>
  );
}

/* ──────────────────────────────────────────────────────────────────────────
 * Phase 4 generic skeleton primitives.
 * All use the bounded shimmer from globals.css (`.animate-pulse` overridden
 * to iteration-count: 8). Decorative — every wrapper gets aria-busy.
 * ────────────────────────────────────────────────────────────────────────── */

export interface CardSkeletonProps {
  /** Render a cover/media block at top (default false). */
  media?: boolean;
  /** Aspect-ratio for the media block. Defaults to 16:9. */
  mediaAspect?: "video" | "square" | "portrait";
  /** Number of body lines (defaults to 2). */
  lines?: number;
  className?: string;
}

const MEDIA_ASPECT: Record<NonNullable<CardSkeletonProps["mediaAspect"]>, string> = {
  video: "aspect-video",
  square: "aspect-square",
  portrait: "aspect-[3/4]",
};

export function CardSkeleton({
  media = false,
  mediaAspect = "video",
  lines = 2,
  className,
}: CardSkeletonProps) {
  return (
    <Card
      size="sm"
      className={cn("h-full", className)}
      aria-busy="true"
      aria-live="polite"
    >
      {media ? (
        <Skeleton className={cn("w-full rounded-none", MEDIA_ASPECT[mediaAspect])} />
      ) : null}
      <CardHeader>
        <Skeleton className="h-4 w-3/4" />
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton
            key={i}
            className={cn("h-3", i === lines - 1 ? "w-2/3" : "w-full")}
          />
        ))}
      </CardContent>
    </Card>
  );
}

export interface ListSkeletonProps {
  count?: number;
  showAvatar?: boolean;
  className?: string;
}

export function ListSkeleton({
  count = 5,
  showAvatar = false,
  className,
}: ListSkeletonProps) {
  return (
    <ul
      className={cn("flex flex-col gap-3", className)}
      aria-busy="true"
      aria-live="polite"
    >
      {Array.from({ length: count }).map((_, i) => (
        <li
          key={i}
          className="flex items-center gap-3 rounded-lg border border-border/60 bg-card p-3"
        >
          {showAvatar ? <Skeleton className="size-9 shrink-0 rounded-full" /> : null}
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-3.5 w-2/5" />
            <Skeleton className="h-3 w-3/5" />
          </div>
          <Skeleton className="h-3 w-10 shrink-0" />
        </li>
      ))}
    </ul>
  );
}

export interface GridSkeletonProps {
  count?: number;
  /** Card variant (media/no-media). */
  media?: boolean;
  mediaAspect?: CardSkeletonProps["mediaAspect"];
  /** Tailwind grid classes override; otherwise sm:2 / md:3 / lg:4. */
  className?: string;
}

export function GridSkeleton({
  count = 8,
  media = true,
  mediaAspect = "video",
  className,
}: GridSkeletonProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4",
        className
      )}
      aria-busy="true"
      aria-live="polite"
    >
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} media={media} mediaAspect={mediaAspect} />
      ))}
    </div>
  );
}

export interface TableSkeletonProps {
  rows?: number;
  cols?: number;
  className?: string;
}

export function TableSkeleton({
  rows = 6,
  cols = 4,
  className,
}: TableSkeletonProps) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-lg border border-border/60 bg-card",
        className
      )}
      aria-busy="true"
      aria-live="polite"
    >
      {/* Header row */}
      <div
        className="grid border-b border-border/60 bg-muted/40 px-3 py-2.5"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      >
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-3 w-2/3" />
        ))}
      </div>
      {/* Body rows */}
      <div className="divide-y divide-border/60">
        {Array.from({ length: rows }).map((_, r) => (
          <div
            key={r}
            className="grid px-3 py-3"
            style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
          >
            {Array.from({ length: cols }).map((__, c) => (
              <Skeleton
                key={c}
                className={cn("h-3", c === cols - 1 ? "w-1/3" : "w-3/4")}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export interface ChartSkeletonProps {
  /** Chart height in pixels. */
  height?: number;
  /** Number of decorative "bars" (defaults to 12). */
  bars?: number;
  className?: string;
}

export function ChartSkeleton({
  height = 220,
  bars = 12,
  className,
}: ChartSkeletonProps) {
  // Deterministic pseudo-random heights — keeps SSR/CSR output stable.
  const heights = React.useMemo(() => {
    const out: number[] = [];
    for (let i = 0; i < bars; i++) {
      // 30%–90% range, sine-ish but stable.
      const t = (Math.sin(i * 1.7) + 1) / 2; // 0..1
      out.push(30 + Math.round(t * 60));
    }
    return out;
  }, [bars]);

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border/60 bg-card p-4",
        className
      )}
      aria-busy="true"
      aria-live="polite"
    >
      {/* Title placeholder */}
      <Skeleton className="h-4 w-1/3" />
      {/* Chart canvas */}
      <div
        className="flex items-end gap-2"
        style={{ height: `${height}px` }}
      >
        {heights.map((h, i) => (
          <Skeleton
            key={i}
            className="flex-1 rounded-md"
            style={{ height: `${h}%` }}
          />
        ))}
      </div>
      {/* X-axis labels */}
      <div className="flex justify-between">
        {Array.from({ length: Math.min(6, bars) }).map((_, i) => (
          <Skeleton key={i} className="h-2.5 w-8" />
        ))}
      </div>
    </div>
  );
}
