"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { StoryCard, type LibraryStory } from "./StoryCard";
import { StoryCardSkeleton } from "@/components/common/Skeletons";
import { cn } from "@/lib/utils";

export interface LibraryGridProps {
  stories: LibraryStory[];
  isLoading?: boolean;
  hasNextPage?: boolean;
  onLoadMore?: () => void;
  onStoryClick?: (story: LibraryStory) => void;
  emptyState?: React.ReactNode;
  isFetchingNextPage?: boolean;
  className?: string;
}

const SKELETON_COUNT = 8;

export function LibraryGrid({
  stories,
  isLoading,
  hasNextPage,
  onLoadMore,
  onStoryClick,
  emptyState,
  isFetchingNextPage,
  className,
}: LibraryGridProps) {
  if (isLoading && stories.length === 0) {
    return (
      <div
        className={cn(
          "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4",
          className
        )}
        aria-busy="true"
      >
        {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
          <StoryCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (!isLoading && stories.length === 0) {
    return <div className={className}>{emptyState}</div>;
  }

  return (
    <div className={cn("flex flex-col gap-6", className)}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {stories.map((s) => (
          <StoryCard
            key={s.id}
            story={s}
            onClick={onStoryClick ? () => onStoryClick(s) : undefined}
          />
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
