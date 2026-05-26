"use client";

/**
 * BookshelfGrid — 3-col responsive grid for locally-persisted forge stories.
 *
 * Distinct from `LibraryGrid` (which paginates server-backed stories).
 */

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { useTranslations } from "next-intl";
import { BookOpen, Plus, Sparkles } from "lucide-react";
import { StoryCard, type LibraryStory } from "./StoryCard";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";
import { cn } from "@/lib/utils";
import type { Story } from "@/types/story";
import { displayStoryTitle } from "@/lib/library/display-helpers";

export interface BookshelfGridProps {
  stories: Story[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onCreate?: () => void;
  className?: string;
}

function toCard(story: Story, untitledFallback: string): LibraryStory {
  return {
    id: story.id,
    title: displayStoryTitle(story, untitledFallback),
    genre: story.genre || undefined,
    chapter_count: story.chapters.length,
    target_chapters: story.targetChapters ?? null,
    cover_url: story.coverUrl ?? undefined,
    created_at: story.createdAt,
  };
}

export function BookshelfGrid({
  stories,
  selectedId,
  onSelect,
  onCreate,
  className,
}: BookshelfGridProps) {
  const reduce = useReducedMotion();
  const t = useTranslations("library");
  if (stories.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title={t("empty")}
        description={t("empty_hint")}
        className={cn(
          "min-h-[320px] rounded-2xl border border-dashed border-border/70 bg-card/35",
          className,
        )}
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button type="button" variant="outline" onClick={() => window.location.assign('/forge/')}>
              <Sparkles className="size-4" aria-hidden />
              {t("open_forge")}
            </Button>
            {onCreate ? (
              <Button type="button" onClick={onCreate}>
                <Plus className="size-4" aria-hidden />
                {t("create_manual")}
              </Button>
            ) : null}
          </div>
        }
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
          <StoryCard story={toCard(story, t("untitled_story"))} onClick={() => onSelect(story.id)} />
        </motion.li>
      ))}
    </ul>
  );
}
