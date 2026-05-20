"use client";

import * as React from "react";
import { motion } from "motion/react";
import { BookOpen } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface LibraryStory {
  id: string;
  title: string;
  genre?: string;
  chapter_count?: number;
  word_count?: number;
  created_at?: string;
  cover_url?: string;
}

export interface StoryCardProps {
  story: LibraryStory;
  onClick?: () => void;
  className?: string;
}

const RELATIVE_FORMATTER =
  typeof Intl !== "undefined" && "RelativeTimeFormat" in Intl
    ? new Intl.RelativeTimeFormat("vi", { numeric: "auto" })
    : null;

const NUMBER_FORMATTER = new Intl.NumberFormat("vi-VN");

function relativeDate(iso?: string): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  if (!RELATIVE_FORMATTER) return new Date(t).toLocaleDateString("vi-VN");
  const diff = (t - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 60) return RELATIVE_FORMATTER.format(Math.round(diff), "second");
  if (abs < 3600) return RELATIVE_FORMATTER.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return RELATIVE_FORMATTER.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 30)
    return RELATIVE_FORMATTER.format(Math.round(diff / 86400), "day");
  if (abs < 86400 * 365)
    return RELATIVE_FORMATTER.format(Math.round(diff / (86400 * 30)), "month");
  return RELATIVE_FORMATTER.format(Math.round(diff / (86400 * 365)), "year");
}

export function StoryCard({ story, onClick, className }: StoryCardProps) {
  const created = relativeDate(story.created_at);
  const interactive = typeof onClick === "function";

  const content = (
    <Card
      size="sm"
      className={cn(
        "relative h-full overflow-hidden transition-shadow duration-[var(--duration-fast)] ease-[var(--ease-out)]",
        interactive && "cursor-pointer hover:shadow-md",
        className
      )}
    >
      <div className="relative">
        {story.cover_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={story.cover_url}
            alt=""
            loading="lazy"
            decoding="async"
            className="aspect-[3/4] w-full object-cover bg-muted"
          />
        ) : (
          <div
            aria-hidden
            className="flex aspect-[3/4] w-full items-center justify-center bg-gradient-to-br from-muted to-muted/60 text-muted-foreground"
          >
            <BookOpen className="size-8" />
          </div>
        )}
        {story.genre ? (
          <Badge
            variant="outline"
            className="absolute top-2 left-2 border-[var(--color-accent,#C5A47E)]/40 bg-[var(--color-accent,#C5A47E)]/15 text-[var(--color-accent,#C5A47E)] backdrop-blur-sm"
          >
            {story.genre}
          </Badge>
        ) : null}
      </div>
      <CardHeader>
        <CardTitle className="line-clamp-2 leading-snug">{story.title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        {typeof story.chapter_count === "number" ? (
          <span className="tabular-nums">
            {NUMBER_FORMATTER.format(story.chapter_count)} chương
          </span>
        ) : null}
        {typeof story.word_count === "number" ? (
          <>
            <span aria-hidden>·</span>
            <span className="tabular-nums">
              {NUMBER_FORMATTER.format(story.word_count)} từ
            </span>
          </>
        ) : null}
        {created ? (
          <>
            <span aria-hidden className="ml-auto" />
            <span>{created}</span>
          </>
        ) : null}
      </CardContent>
    </Card>
  );

  if (!interactive) return content;

  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileHover={{ y: -2 }}
      transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
      className="block w-full text-left focus-visible:rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      aria-label={story.title}
    >
      {content}
    </motion.button>
  );
}
