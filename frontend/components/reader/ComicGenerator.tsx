"use client";

/**
 * ComicGenerator — on-demand, per-story comic-image control for the Library.
 *
 * Comics are NO LONGER auto-generated when the pipeline finishes; the user
 * triggers them here, per story, in the reader/Library detail view.
 *
 * Backend contract (api/image_routes.py):
 *   GET  /api/images/{sessionId}/status   → per-chapter render state
 *   POST /api/images/{sessionId}/generate → incremental / single / full
 *
 * `sessionId` is the checkpoint filename the Library addresses a story by
 * (e.g. `story_<id>.json`) — the same id `useStory()` already loads with.
 *
 * Behaviours handled:
 *   - Incremental (default button): only chapters lacking panels. This is what
 *     makes "Continue"-added chapters get comics consistent with old ones.
 *   - Single-chapter + full regenerate.
 *   - 409 (a generate already running) → friendly "đang tạo…" toast + refetch.
 *   - provider "none" / empty result → prompt to configure a provider.
 *   - On success, refetch /status so newly-filled chapters flip to "has images".
 */

import * as React from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import {
  ImageIcon,
  Loader2,
  RefreshCw,
  CheckCircle2,
  Circle,
  AlertCircle,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { ApiError } from "@/lib/api/client";
import { ComicPanels } from "@/components/reader/ComicPanels";
import {
  getComicStatus,
  generateMissingImages,
  generateAllImages,
  generateChapterImage,
  type ComicStatusResponse,
  type ChapterComicStatus,
} from "@/lib/api/illustration";

export interface ComicGeneratorProps {
  /** Checkpoint filename / session id the story is addressed by. */
  sessionId: string;
  className?: string;
}

type RowState = "ready" | "pending" | "generating" | "error";

export function ComicGenerator({ sessionId, className }: ComicGeneratorProps) {
  const t = useTranslations("comic");
  const qc = useQueryClient();

  const statusQuery = useQuery<ComicStatusResponse, Error>({
    queryKey: ["comic-status", sessionId],
    queryFn: () => getComicStatus(sessionId),
    enabled: !!sessionId,
    staleTime: 15_000,
  });

  // `null` = a whole-story generate (incremental / full); number = one chapter.
  const [busyChapter, setBusyChapter] = React.useState<number | "all" | null>(
    null,
  );
  const [errored, setErrored] = React.useState<Record<number, boolean>>({});
  const [expanded, setExpanded] = React.useState<Record<number, boolean>>({});

  const data = statusQuery.data;
  const providerMissing = data?.provider === "none";

  const refetchStatus = React.useCallback(async () => {
    await qc.invalidateQueries({ queryKey: ["comic-status", sessionId] });
  }, [qc, sessionId]);

  const handleApiError = React.useCallback(
    (e: unknown, chapter?: number) => {
      if (e instanceof ApiError && e.status === 409) {
        toast.message(t("in_flight"));
        void refetchStatus();
        return;
      }
      if (typeof chapter === "number") {
        setErrored((prev) => ({ ...prev, [chapter]: true }));
      }
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(t("failed"), { description: msg });
    },
    [refetchStatus, t],
  );

  const afterGenerate = React.useCallback(
    (count: number) => {
      if (count === 0) {
        toast.message(t("no_new"));
      } else {
        toast.success(t("done", { count }));
      }
      void refetchStatus();
    },
    [refetchStatus, t],
  );

  // Incremental (default) — only chapters lacking panels. Includes Continue's
  // new chapters. Idempotent on the backend.
  const handleGenerateMissing = React.useCallback(async () => {
    if (busyChapter !== null) return;
    setBusyChapter("all");
    setErrored({});
    try {
      const res = await generateMissingImages(sessionId);
      afterGenerate(res.count);
    } catch (e) {
      handleApiError(e);
    } finally {
      setBusyChapter(null);
    }
  }, [busyChapter, sessionId, afterGenerate, handleApiError]);

  const handleRegenerateAll = React.useCallback(async () => {
    if (busyChapter !== null) return;
    setBusyChapter("all");
    setErrored({});
    try {
      const res = await generateAllImages(sessionId);
      afterGenerate(res.count);
    } catch (e) {
      handleApiError(e);
    } finally {
      setBusyChapter(null);
    }
  }, [busyChapter, sessionId, afterGenerate, handleApiError]);

  const handleRegenerateChapter = React.useCallback(
    async (chapter: number) => {
      if (busyChapter !== null) return;
      setBusyChapter(chapter);
      setErrored((prev) => ({ ...prev, [chapter]: false }));
      try {
        const res = await generateChapterImage(sessionId, chapter);
        afterGenerate(res.count);
      } catch (e) {
        handleApiError(e, chapter);
      } finally {
        setBusyChapter(null);
      }
    },
    [busyChapter, sessionId, afterGenerate, handleApiError],
  );

  // ---- Render -------------------------------------------------------------

  if (statusQuery.isLoading) {
    return (
      <div
        className={cn("flex items-center gap-2 text-sm text-muted-foreground", className)}
      >
        <Loader2 className="size-4 animate-spin" aria-hidden />
        {t("loading")}
      </div>
    );
  }

  // 404 = story has no server-side checkpoint (e.g. localStorage-only story).
  if (statusQuery.isError) {
    const err = statusQuery.error;
    const notFound = err instanceof ApiError && err.status === 404;
    return (
      <p className={cn("text-sm text-muted-foreground", className)}>
        {notFound ? t("unavailable") : (err?.message ?? t("failed"))}
      </p>
    );
  }

  if (!data) return null;

  const chapters = data.chapters;
  const allHaveImages =
    chapters.length > 0 && data.chapters_with_images === chapters.length;
  const busyAll = busyChapter === "all";

  const rowState = (ch: ChapterComicStatus): RowState => {
    if (busyChapter === ch.chapter_number || (busyAll && !ch.has_images)) {
      return "generating";
    }
    if (errored[ch.chapter_number]) return "error";
    return ch.has_images ? "ready" : "pending";
  };

  return (
    <section
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-border/60 bg-card/70 p-4",
        className,
      )}
      aria-label={t("title")}
    >
      <header className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <ImageIcon className="size-4 text-muted-foreground" aria-hidden />
          <h3 className="text-sm font-semibold">{t("title")}</h3>
        </div>
        <span className="text-xs tabular-nums text-muted-foreground">
          {t("progress", {
            done: data.chapters_with_images,
            total: data.total_chapters,
          })}
        </span>
      </header>

      {providerMissing ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-700 dark:text-amber-300">
          <AlertCircle className="size-4 shrink-0" aria-hidden />
          <span className="flex-1">{t("provider_missing")}</span>
          <Link
            href="/settings"
            className="font-medium underline underline-offset-2"
          >
            {t("open_settings")}
          </Link>
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={() => void handleGenerateMissing()}
          disabled={busyChapter !== null || providerMissing || allHaveImages}
          className="gap-1.5"
        >
          {busyAll ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <ImageIcon className="size-4" aria-hidden />
          )}
          {data.chapters_with_images > 0 ? t("generate_new") : t("generate")}
        </Button>
        {data.chapters_with_images > 0 ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => void handleRegenerateAll()}
            disabled={busyChapter !== null || providerMissing}
            className="gap-1.5"
          >
            <RefreshCw
              className={cn("size-4", busyAll && "animate-spin")}
              aria-hidden
            />
            {t("regenerate_all")}
          </Button>
        ) : null}
      </div>

      {chapters.length > 0 ? (
        <ul role="list" className="divide-y divide-border/40 rounded-md border border-border/60">
          {chapters.map((ch) => {
            const state = rowState(ch);
            const isOpen = !!expanded[ch.chapter_number];
            const canExpand = ch.has_images && ch.image_urls.length > 0;
            return (
              <li key={ch.chapter_number} className="flex flex-col">
                <div className="flex items-center gap-2 p-2 text-xs">
                  <StateIcon state={state} />
                  <span className="w-16 shrink-0 font-mono text-muted-foreground">
                    {t("chapter", { number: ch.chapter_number })}
                  </span>
                  <span className="line-clamp-1 flex-1">{ch.title}</span>
                  {ch.has_images ? (
                    <Badge variant="secondary" className="shrink-0 tabular-nums">
                      {t("panels_count", { count: ch.image_count })}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="shrink-0">
                      {t(`state_${state}` as const)}
                    </Badge>
                  )}
                  {canExpand ? (
                    <Button
                      type="button"
                      size="icon"
                      variant="ghost"
                      className="size-7"
                      aria-label={isOpen ? t("hide_panels") : t("show_panels")}
                      title={isOpen ? t("hide_panels") : t("show_panels")}
                      onClick={() =>
                        setExpanded((prev) => ({
                          ...prev,
                          [ch.chapter_number]: !prev[ch.chapter_number],
                        }))
                      }
                    >
                      <ChevronDown
                        className={cn(
                          "size-4 transition-transform",
                          isOpen && "rotate-180",
                        )}
                        aria-hidden
                      />
                    </Button>
                  ) : null}
                  <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    className="size-7"
                    disabled={busyChapter !== null || providerMissing}
                    aria-label={t("regenerate_chapter")}
                    title={t("regenerate_chapter")}
                    onClick={() => void handleRegenerateChapter(ch.chapter_number)}
                  >
                    <RefreshCw
                      className={cn(
                        "size-4",
                        busyChapter === ch.chapter_number && "animate-spin",
                      )}
                      aria-hidden
                    />
                  </Button>
                </div>
                {canExpand && isOpen ? (
                  <div className="px-2 pb-2">
                    <ComicPanels
                      images={ch.image_urls}
                      alt={t("chapter", { number: ch.chapter_number })}
                    />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}

function StateIcon({ state }: { state: RowState }) {
  if (state === "generating") {
    return <Loader2 className="size-4 shrink-0 animate-spin text-primary" aria-hidden />;
  }
  if (state === "ready") {
    return <CheckCircle2 className="size-4 shrink-0 text-emerald-500" aria-hidden />;
  }
  if (state === "error") {
    return <AlertCircle className="size-4 shrink-0 text-destructive" aria-hidden />;
  }
  return <Circle className="size-4 shrink-0 text-muted-foreground" aria-hidden />;
}
