"use client";

/**
 * BookshelfGrid — 3-col responsive grid for locally-persisted forge stories.
 *
 * Distinct from `LibraryGrid` (which paginates server-backed stories).
 */

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { BookOpen } from "lucide-react";
import { StoryCard, type LibraryStory } from "./StoryCard";
import { EmptyState } from "@/components/common/EmptyState";
import { cn } from "@/lib/utils";
import type { Story } from "@/types/story";

export interface BookshelfGridProps {
  stories: Story[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  className?: string;
}

function toCard(story: Story): LibraryStory {
  return {
    id: story.id,
    title: story.title,
    genre: story.genre || undefined,
    chapter_count: story.chapters.length,
    cover_url: story.coverUrl ?? undefined,
    created_at: story.createdAt,
  };
}

export function BookshelfGrid({
  stories,
  selectedId,
  onSelect,
  className,
}: BookshelfGridProps) {
  const reduce = useReducedMotion();
  if (stories.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="Kho truyện trống"
        description="Forge một câu ý tưởng hoặc tạo truyện thủ công để bắt đầu."
      />
    );
  }

  return (
    <ul
      role="list"
      className={cn(
        "grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3",
        className,
      )}
    >
      {stories.map((story, idx) => (
        <motion.li
          key={story.id}
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={reduce ? undefined : { opacity: 1, y: 0 }}
          transition={reduce ? undefined : { duration: 0.25, delay: Math.min(idx * 0.03, 0.3) }}
          className={cn(
            "relative",
            selectedId === story.id &&
              "rounded-xl outline outline-2 outline-offset-2 outline-[var(--color-accent,#C5A47E)]",
          )}
        >
          <StoryCard story={toCard(story)} onClick={() => onSelect(story.id)} />
        </motion.li>
      ))}
    </ul>
  );
}
