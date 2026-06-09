"use client";

/**
 * LibraryComicGenerator — on-demand comic (truyện tranh) control for
 * localStorage-only Library stories.
 *
 * These stories have NO backend checkpoint, so this operates purely on the
 * payload endpoint `POST /api/images/library/generate` (via the
 * `generateLibrary*` wrappers) and persists the returned `chapter_images` back
 * onto `Story.chapters[i].images` through the library store. It is the
 * localStorage counterpart of the checkpoint-based `reader/ComicGenerator.tsx`
 * — DO NOT confuse the two.
 *
 * Per-chapter state is derived from `Story.chapters[i].images` (non-empty =>
 * already illustrated). The primary button flips label between "tạo mới" and
 * "tạo cho chương mới" depending on whether anything is illustrated yet, so the
 * "Continue" case (append chapters → fill only the new ones) reads naturally.
 */

import * as React from "react";
import Link from "next/link";
import { ImageIcon, RefreshCw, AlertTriangle, Settings } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ComicPanels } from "@/components/reader/ComicPanels";
import { cn } from "@/lib/utils";
import { useLibraryStore } from "@/stores/library-store";
import {
  generateLibraryMissingImages,
  generateLibraryChapterImage,
  generateLibraryAllImages,
  type GenerateImagesResponse,
} from "@/lib/api/illustration";
import { ApiError } from "@/lib/api/client";
import type { Story } from "@/types/story";

export interface LibraryComicGeneratorProps {
  story: Story;
  className?: string;
}

/** In-flight target: "all"/"missing" = whole-story run, number = single chapter. */
type Pending = "missing" | "all" | number | null;

export function LibraryComicGenerator({
  story,
  className,
}: LibraryComicGeneratorProps) {
  const t = useTranslations("library");
  const setStoryChapterImages = useLibraryStore((s) => s.setStoryChapterImages);

  const [pending, setPending] = React.useState<Pending>(null);
  const [noProvider, setNoProvider] = React.useState(false);

  const total = story.chapters.length;
  const illustrated = React.useMemo(
    () => story.chapters.filter((ch) => (ch.images?.length ?? 0) > 0).length,
    [story.chapters],
  );
  const hasChapters = total > 0;
  const busy = pending !== null;

  // Once SOME chapters have panels, the primary action is "fill the new ones".
  const primaryLabel =
    illustrated > 0 ? t("comic_generate_more") : t("comic_generate_new");

  const persist = React.useCallback(
    (res: GenerateImagesResponse) => {
      // Backend returns the FULL current map (1-based chapter -> URLs).
      if (res.chapter_images && Object.keys(res.chapter_images).length > 0) {
        setStoryChapterImages(story.id, res.chapter_images);
      }
    },
    [setStoryChapterImages, story.id],
  );

  const run = React.useCallback(
    async (
      target: Pending,
      call: () => Promise<GenerateImagesResponse>,
    ) => {
      if (busy) return;
      setPending(target);
      try {
        const res = await call();
        // provider "none" => count 0, nothing generated.
        if (res.count === 0 && Object.keys(res.chapter_images ?? {}).length === 0) {
          setNoProvider(true);
          return;
        }
        setNoProvider(false);
        persist(res);
        if (res.count > 0) {
          toast.success(t("comic_done", { count: res.count }));
        } else {
          toast.info(t("comic_nothing_missing"));
        }
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 409) {
            toast.error(t("comic_busy"));
            return;
          }
          if (err.status === 400) {
            toast.error(t("comic_failed"), { description: err.message });
            return;
          }
        }
        toast.error(t("comic_failed"), {
          description: err instanceof Error ? err.message : String(err),
        });
      } finally {
        setPending(null);
      }
    },
    [busy, persist, t],
  );

  const handleGenerate = React.useCallback(() => {
    void run("missing", () => generateLibraryMissingImages(story));
  }, [run, story]);

  const handleRegenerateAll = React.useCallback(() => {
    void run("all", () => generateLibraryAllImages(story));
  }, [run, story]);

  const handleRegenerateChapter = React.useCallback(
    (chapterNumber: number) => {
      void run(chapterNumber, () =>
        generateLibraryChapterImage(story, chapterNumber),
      );
    },
    [run, story],
  );

  if (!hasChapters) {
    return (
      <section className={cn("space-y-2", className)} aria-label={t("comic_title")}>
        <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <ImageIcon className="size-3.5" aria-hidden />
          {t("comic_title")}
        </h3>
        <p className="text-xs text-muted-foreground">{t("comic_no_chapters")}</p>
      </section>
    );
  }

  return (
    <section className={cn("space-y-2.5", className)} aria-label={t("comic_title")}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <ImageIcon className="size-3.5" aria-hidden />
          {t("comic_title")}
        </h3>
        <span className="text-[11px] tabular-nums text-muted-foreground">
          {t("comic_progress", { done: illustrated, total })}
        </span>
      </div>

      {noProvider ? (
        <div className="flex items-start gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-[11px] text-amber-700 dark:text-amber-300">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <div className="space-y-1">
            <p>{t("comic_no_provider")}</p>
            <Link
              href="/settings"
              className="inline-flex items-center gap-1 font-medium underline underline-offset-2"
            >
              <Settings className="size-3" aria-hidden />
              {t("comic_open_settings")}
            </Link>
          </div>
        </div>
      ) : null}

      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          onClick={handleGenerate}
          disabled={busy || noProvider}
          className="flex-1 gap-1.5"
        >
          {pending === "missing" ? (
            <RefreshCw className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <ImageIcon className="size-3.5" aria-hidden />
          )}
          {pending === "missing" ? t("comic_generating") : primaryLabel}
        </Button>
        {illustrated > 0 ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={handleRegenerateAll}
            disabled={busy || noProvider}
            aria-label={t("comic_regenerate_all")}
            title={t("comic_regenerate_all")}
            className="gap-1.5"
          >
            <RefreshCw
              className={cn("size-3.5", pending === "all" && "animate-spin")}
              aria-hidden
            />
          </Button>
        ) : null}
      </div>

      <ul role="list" className="space-y-1.5">
        {story.chapters.map((ch, i) => {
          const n = i + 1;
          const has = (ch.images?.length ?? 0) > 0;
          const rowBusy = pending === n;
          return (
            <li key={ch.id} className="space-y-1.5">
              <div className="flex items-center gap-2 text-xs">
                <span className="w-6 shrink-0 font-mono text-muted-foreground">
                  {n}
                </span>
                <span className="line-clamp-1 flex-1">{ch.title}</span>
                <Badge variant={has ? "default" : "outline"} className="shrink-0">
                  {has ? t("comic_chapter_has") : t("comic_chapter_missing")}
                </Badge>
                {has ? (
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    onClick={() => handleRegenerateChapter(n)}
                    disabled={busy || noProvider}
                    aria-label={t("comic_regenerate_chapter")}
                    title={t("comic_regenerate_chapter")}
                    className="size-7 shrink-0"
                  >
                    <RefreshCw
                      className={cn("size-3.5", rowBusy && "animate-spin")}
                      aria-hidden
                    />
                  </Button>
                ) : null}
              </div>
              {has ? (
                <ComicPanels
                  images={ch.images}
                  alt={`${t("comic_title")} — ${ch.title}`}
                  loading={rowBusy}
                />
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
