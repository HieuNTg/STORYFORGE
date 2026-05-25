"use client";

import * as React from "react";
import Link from "next/link";
import { BarChart3, BookOpen, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/common/EmptyState";
import { rehydrateLibrary, useLibraryStore } from "@/stores/library-store";

import { useTranslations } from "next-intl";

export function AnalyticsStartScreen() {
  const stories = useLibraryStore((s) => s.stories);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const t = useTranslations("analytics");
  const tGenres = useTranslations("genres");
  const tLib = useTranslations("library");
  const tExport = useTranslations("export");

  React.useEffect(() => {
    rehydrateLibrary();
  }, []);

  const getGenreLabel = (genre?: string) => {
    if (!genre) return t("no_genre");
    const key = genre.toLowerCase().replace(/\s+/g, "_");
    return tGenres.has(key) ? tGenres(key as any) : genre;
  };

  if (!hydrated) {
    return (
      <div className="rounded-2xl border border-border/60 bg-card/35 p-8 text-sm text-muted-foreground">
        {t("loading_library")}
      </div>
    );
  }

  if (stories.length === 0) {
    return (
      <EmptyState
        icon={BarChart3}
        title={t("empty_title")}
        description={t("empty_desc")}
        className="min-h-[320px] rounded-2xl border border-dashed border-border/70 bg-card/35"
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button asChild variant="outline">
              <Link href="/forge/">
                <Sparkles className="size-4" aria-hidden />
                {tLib("open_forge")}
              </Link>
            </Button>
            <Button asChild>
              <Link href="/library/">
                <BookOpen className="size-4" aria-hidden />
                {tExport("open_library")}
              </Link>
            </Button>
          </div>
        }
      />
    );
  }

  return (
    <section className="rounded-2xl border border-border/70 bg-card/35 p-4">
      <div className="mb-4">
        <h2 className="font-serif text-lg text-foreground">{t("select_story_title")}</h2>
        <p className="text-sm text-muted-foreground">
          {t("select_story_desc")}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {stories.map((story) => (
          <Link
            key={story.id}
            href={`/analytics/${story.id}/`}
            className="group rounded-xl border border-border bg-background/55 p-4 transition hover:-translate-y-0.5 hover:border-accent/60 hover:bg-accent/10 hover:shadow-md hover:shadow-accent/10"
          >
            <div className="flex items-start gap-3">
              <span className="rounded-lg border border-border/60 bg-background/70 p-2 text-muted-foreground transition-colors group-hover:text-accent">
                <BarChart3 className="size-4" aria-hidden />
              </span>
              <div className="min-w-0">
                <h3 className="truncate text-sm font-semibold text-foreground">
                  {story.title}
                </h3>
                <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                  {getGenreLabel(story.genre)} · {t("chapters_count", { count: story.chapters.length })}
                </p>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
