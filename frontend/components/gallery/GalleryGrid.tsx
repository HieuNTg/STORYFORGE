"use client";

/**
 * GalleryGrid — final visual treatment (Phase 4 UI design).
 *
 * Layout: responsive grid, 2 / 3 / 4 columns at sm / md / lg, single-column on
 * mobile. gap-4 throughout. Bounded shimmer skeleton while initially loading.
 *
 * API contract preserved from Frontend Developer stub:
 *   - props: { items, isLoading, hasNextPage, isFetchingNextPage,
 *              onLoadMore, onOpen, emptyState, className }
 */

import * as React from "react";
import { Button } from "@/components/ui/button";
import { GridSkeleton } from "@/components/common/Skeletons";
import { cn } from "@/lib/utils";
import type { GalleryItem } from "@/lib/api/gallery";
import { GalleryCard } from "./GalleryCard";

export interface GalleryGridProps {
  items: GalleryItem[];
  isLoading?: boolean;
  hasNextPage?: boolean;
  isFetchingNextPage?: boolean;
  onLoadMore?: () => void;
  onOpen?: (item: GalleryItem) => void;
  emptyState?: React.ReactNode;
  /** Skeleton count for the initial-loading state. */
  skeletonCount?: number;
  className?: string;
}

const GRID_CLASSES =
  "grid grid-cols-1 gap-4 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4";

export function GalleryGrid({
  items,
  isLoading,
  hasNextPage,
  isFetchingNextPage,
  onLoadMore,
  onOpen,
  emptyState,
  skeletonCount = 8,
  className,
}: GalleryGridProps) {
  if (isLoading && items.length === 0) {
    return (
      <GridSkeleton
        count={skeletonCount}
        media
        mediaAspect="video"
        className={cn(GRID_CLASSES, className)}
      />
    );
  }
  if (!isLoading && items.length === 0) {
    return <div className={className}>{emptyState}</div>;
  }
  return (
    <div className={cn("flex flex-col gap-6", className)}>
      <div className={GRID_CLASSES}>
        {items.map((it) => (
          <GalleryCard key={it.share_id} item={it} onOpen={onOpen} />
        ))}
      </div>
      {hasNextPage ? (
        <div className="flex justify-center">
          <Button
            variant="outline"
            onClick={onLoadMore}
            disabled={isFetchingNextPage}
            aria-busy={isFetchingNextPage}
          >
            {isFetchingNextPage ? "Đang tải..." : "Tải thêm"}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
