"use client";

/**
 * LibraryComicGenerator — on-demand comic (truyện tranh) control for
 * localStorage-only Library stories.
 *
 * These stories have NO backend checkpoint, so this operates purely on the
 * async payload job endpoints (`submitLibraryComicJob` → `getLibraryComicJob`)
 * and persists the polled `chapter_images` back onto `Story.chapters[i].images`
 * through the library store. It is the localStorage counterpart of the
 * checkpoint-based `reader/ComicGenerator.tsx` — DO NOT confuse the two.
 *
 * Phase B (async): a single whole-story (or single-chapter) job is submitted
 * once; the backend returns 202 + `job_id` and runs generation off the request
 * thread. We poll for accreting `chapter_images` and persist each illustrated
 * chapter incrementally, so the run survives proxy timeouts and renders panels
 * as they land. See docs/comic-async-generation-phase-b-proposal.md §2.6.
 *
 * Per-chapter state is derived from `Story.chapters[i].images` (non-empty =>
 * already illustrated). The primary button flips label between "tạo mới" and
 * "tạo cho chương mới" depending on whether anything is illustrated yet, so the
 * "Continue" case (append chapters → fill only the new ones) reads naturally.
 */

import * as React from "react";
import Link from "next/link";
import { ImageIcon, RefreshCw, AlertTriangle, Settings, BookOpen } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { useLibraryStore } from "@/stores/library-store";
import {
  submitLibraryComicJob,
  getLibraryComicJob,
  type LibraryJobStatus,
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
  // Per-chapter loop progress (done/total) shown while a multi-chapter run is
  // in flight. null = idle.
  const [progress, setProgress] = React.useState<{ done: number; total: number } | null>(null);

  // Tracks whether the component is still mounted so we never call setState
  // after an await resolves post-unmount. Flipped false by the cleanup effect.
  const mountedRef = React.useRef(true);
  // Pending poll timer; cleared on unmount so polling stops with the component.
  const pollTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (pollTimerRef.current !== null) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

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
    (chapterImages: LibraryJobStatus["chapter_images"]) => {
      // Backend accretes the FULL current map (1-based chapter -> URLs). The
      // store merges, so other chapters are preserved (library-store.ts:103).
      if (chapterImages && Object.keys(chapterImages).length > 0) {
        setStoryChapterImages(story.id, chapterImages);
      }
    },
    [setStoryChapterImages, story.id],
  );

  // Submit ONE async job, then poll it to terminal state. Phase B moves the
  // generation off the request thread: POST returns 202 + job_id in ms, the
  // backend runs every chapter server-side, and we poll for accreting
  // `chapter_images`, persisting + rendering each chapter as it lands. This
  // survives the dev-proxy idle timeout that the Phase A per-chapter chunking
  // existed to dodge, and the run no longer dies if the request disconnects.
  //
  // Poll cadence: 2500ms base; if `chapters_done` is unchanged for 3 polls in a
  // row, back off (×2, capped 8000ms); reset to 2500ms whenever it advances.
  const runJob = React.useCallback(
    async (
      opts: { chapter?: number; only_missing?: boolean },
      target: Pending,
    ) => {
      if (busy) return;
      setPending(target);
      setProgress(null);

      const finish = () => {
        if (!mountedRef.current) return;
        setPending(null);
        setProgress(null);
      };

      let jobId: string;
      try {
        const accepted = await submitLibraryComicJob(story, opts);
        // 200 + already_running => an identical-scope job was already in flight;
        // just attach to it (no toast). 202 => freshly queued. Either way we own
        // the returned job_id from here.
        jobId = accepted.job_id;
        if (mountedRef.current) setNoProvider(false);
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 409) {
            toast.error(t("comic_busy"));
            finish();
            return;
          }
          if (err.status === 400) {
            toast.error(t("comic_failed"), { description: err.message });
            finish();
            return;
          }
        }
        toast.error(t("comic_failed"), {
          description: err instanceof Error ? err.message : String(err),
        });
        finish();
        return;
      }

      const BASE_INTERVAL = 2500;
      const MAX_INTERVAL = 8000;
      let interval = BASE_INTERVAL;
      let lastDone = -1;
      let stalls = 0;

      const poll = async () => {
        if (!mountedRef.current) return;
        let status: LibraryJobStatus;
        try {
          status = await getLibraryComicJob(jobId);
        } catch (err) {
          if (!mountedRef.current) return;
          // A 404 (TTL-evicted / restarted server) or transient error ends the
          // run; completed chapters are already persisted in localStorage.
          toast.error(t("comic_failed"), {
            description: err instanceof Error ? err.message : String(err),
          });
          finish();
          return;
        }
        if (!mountedRef.current) return;

        // Incremental render: persist whatever chapters have landed so far.
        persist(status.chapter_images);
        setProgress({
          done: status.chapters_done,
          total: status.total_chapters,
        });

        // Only a genuinely-unconfigured provider (config === "none") locks the
        // UI: the backend can never produce output, so prompt Settings. A run
        // that produced zero images *with* a provider configured (e.g. a
        // transient FlowKit worker drop) must NOT latch this flag — doing so
        // disables the retry buttons and traps the user until a page reload.
        // That zero-output case is surfaced as a retryable toast below.
        if (status.provider === "none") {
          setNoProvider(true);
        }

        if (
          status.state === "done" ||
          status.state === "error" ||
          status.state === "cancelled"
        ) {
          if (status.state === "done") {
            if (status.count > 0) {
              toast.success(t("comic_done", { count: status.count }));
            } else if (target === "missing" && status.total_chapters === 0) {
              // A "fill missing" run that targeted NO chapters (the backend's
              // only_missing filter found every chapter already illustrated).
              // `total_chapters` == the number of chapters the job actually
              // targeted, so 0 here means genuinely nothing was missing.
              // Informational, not a failure.
              toast.info(t("comic_nothing_missing"));
            } else {
              // Chapters WERE targeted but produced zero images => generation
              // genuinely failed, commonly because the FlowKit worker isn't
              // connected (or the selected provider returned nothing). This
              // also covers all / single-chapter regenerates. Retryable —
              // buttons stay live so the user can fix the provider and retry.
              toast.error(t("comic_no_images"));
            }
          } else if (status.state === "error") {
            toast.error(t("comic_failed"), {
              description: status.error ?? undefined,
            });
          } else {
            // cancelled — reuse the busy/info copy (no dedicated i18n key).
            toast.info(t("comic_busy"));
          }
          finish();
          return;
        }

        // Adaptive backoff on a stalled job; reset the moment progress advances.
        if (status.chapters_done > lastDone) {
          lastDone = status.chapters_done;
          stalls = 0;
          interval = BASE_INTERVAL;
        } else {
          stalls += 1;
          if (stalls >= 3) {
            interval = Math.min(interval * 2, MAX_INTERVAL);
            stalls = 0;
          }
        }
        pollTimerRef.current = setTimeout(() => {
          void poll();
        }, interval);
      };

      void poll();
    },
    [busy, persist, story, t],
  );

  const handleGenerate = React.useCallback(() => {
    void runJob({ only_missing: true }, "missing");
  }, [runJob]);

  const handleRegenerateAll = React.useCallback(() => {
    void runJob({ only_missing: false }, "all");
  }, [runJob]);

  const handleRegenerateChapter = React.useCallback(
    (chapterNumber: number) => {
      void runJob({ chapter: chapterNumber }, chapterNumber);
    },
    [runJob],
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
          {pending === "missing"
            ? progress
              ? `${t("comic_generating")} ${progress.done}/${progress.total}`
              : t("comic_generating")
            : primaryLabel}
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
                  <>
                    {/* Reading happens in the Reader (/reader) — the Library
                        only manages generation; see CEO call 2026-06-10. */}
                    <Button
                      asChild
                      size="icon"
                      variant="ghost"
                      aria-label={t("comic_read_chapter")}
                      title={t("comic_read_chapter")}
                      className="size-7 shrink-0"
                    >
                      <Link
                        href={`/reader/?id=${encodeURIComponent(story.id)}&chapter=${n}`}
                      >
                        <BookOpen className="size-3.5" aria-hidden />
                      </Link>
                    </Button>
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
                  </>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
