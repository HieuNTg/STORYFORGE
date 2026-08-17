"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, BookOpen, ListChecks, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { rehydrateLibrary, useLibraryStore } from "@/stores/library-store";
import { usePostStream } from "@/lib/sse/usePostStream";
import {
  buildContinueBody,
  CONTINUE_LIBRARY_URL,
  fetchContinueOutlines,
  type ContinuationOutline,
  type ContinueDoneData,
  type ContinueRequestBody,
} from "@/lib/api/continueStory";
import type { StoryChapter } from "@/types/story";
import { displayStoryTitle } from "@/lib/library/display-helpers";
import { getChapterDefault, getChapterRange } from "@/lib/library/chapter-defaults";
import {
  clampWordCount,
  MAX_WORD_COUNT,
  MIN_WORD_COUNT,
  suggestWordCount,
} from "@/lib/library/chapter-length";

/** Matches `ContinueLibraryRequest.direction` (max_length=2000) on the backend. */
const MAX_DIRECTION_LEN = 2000;

export function ContinueStoryScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryId = searchParams?.get("id") ?? null;
  const t = useTranslations("continue_screen");

  const stories = useLibraryStore((s) => s.stories);
  const selectedId = useLibraryStore((s) => s.selectedId);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const selectStory = useLibraryStore((s) => s.selectStory);
  const appendChapter = useLibraryStore((s) => s.appendChapter);
  const updateStory = useLibraryStore((s) => s.updateStory);

  const [storyId, setStoryId] = React.useState("");
  const [chapterCount, setChapterCount] = React.useState(1);
  const [direction, setDirection] = React.useState("");
  /** null = follow the story's own rhythm (see `suggestWordCount`). */
  const [wordCountOverride, setWordCountOverride] = React.useState<number | null>(
    null,
  );
  /**
   * A reviewed plan, tagged with the story+batch it was made for. Keeping the
   * key on the value (instead of resetting via an effect) means a plan simply
   * stops applying when the user switches story or batch size — no cascading
   * render, no stale outlines written against the wrong chapters.
   */
  const [plan, setPlan] = React.useState<{
    key: string;
    outlines: ContinuationOutline[];
  } | null>(null);
  const [isPlanning, setIsPlanning] = React.useState(false);
  const [isWriting, setIsWriting] = React.useState(false);
  const [progressLine, setProgressLine] = React.useState("");
  const [written, setWritten] = React.useState(0);
  /**
   * Body of the in-flight continuation. `usePostStream` keys off this
   * reference, so it is set once per run and cleared when the run settles —
   * never rebuilt during render.
   */
  const [pendingBody, setPendingBody] = React.useState<ContinueRequestBody | null>(
    null,
  );

  React.useEffect(() => {
    rehydrateLibrary();
  }, []);

  React.useEffect(() => {
    if (queryId && stories.some((s) => s.id === queryId)) {
      setStoryId(queryId);
      selectStory(queryId);
      return;
    }
    if (!storyId && selectedId && stories.some((s) => s.id === selectedId)) {
      setStoryId(selectedId);
      return;
    }
    if (!storyId && stories.length > 0) setStoryId(stories[0].id);
  }, [queryId, selectedId, selectStory, stories, storyId]);

  const story = React.useMemo(
    () => stories.find((s) => s.id === storyId) ?? null,
    [stories, storyId],
  );

  const target = story?.targetChapters ?? null;
  const writtenCount = story?.chapters.length ?? 0;
  const remaining = target == null ? null : Math.max(0, target - writtenCount);
  const atTarget = remaining != null && remaining === 0;

  const maxBatch = remaining == null ? 10 : Math.max(1, remaining);

  const suggestedWordCount = React.useMemo(
    () => suggestWordCount(story?.chapters ?? []),
    [story],
  );
  const effectiveWordCount = wordCountOverride ?? suggestedWordCount;

  const planKey = `${storyId}:${chapterCount}`;
  const outlines = plan?.key === planKey ? plan.outlines : null;

  React.useEffect(() => {
    if (chapterCount > maxBatch) setChapterCount(maxBatch);
  }, [chapterCount, maxBatch]);

  /**
   * False while a run is in flight and has not yet produced a terminal frame.
   * The SSE stream always closes after `done`/`error`, so `onClose` needs this
   * to tell "closed normally" from "closed on us mid-run".
   */
  const settledRef = React.useRef(true);

  const finish = React.useCallback((message?: string) => {
    settledRef.current = true;
    setPendingBody(null);
    setIsWriting(false);
    setProgressLine(message ?? "");
  }, []);

  const handleDone = React.useCallback(
    (data: ContinueDoneData) => {
      const chapters = data.new_chapters ?? [];
      if (!story || chapters.length === 0) {
        finish();
        toast.error(t("toast_failed_title"), { description: t("toast_no_chapters") });
        return;
      }
      const now = new Date().toISOString();
      chapters.forEach((ch, i) => {
        const chapter: StoryChapter = {
          id: `chapter-${Date.now().toString(36)}-${i}`,
          title: ch.title || `Chương ${ch.number}`,
          content: ch.content,
          summary: ch.summary,
          badge: "Ch",
          status: (data.enhanced_chapters ?? 0) > 0 ? "enhanced" : "ready",
          images: [],
          createdAt: now,
        };
        appendChapter(story.id, chapter);
      });
      setWritten(chapters.length);
      finish();
      toast.success(t("toast_success_title"), {
        description: t("toast_success_body", { count: chapters.length }),
      });
      router.push(`/reader/?id=${encodeURIComponent(story.id)}`);
    },
    [appendChapter, finish, router, story, t],
  );

  const handleMessage = React.useCallback(
    (ev: { data: string }) => {
      if (!ev.data) return;
      let frame: { type?: string; data?: unknown };
      try {
        frame = JSON.parse(ev.data);
      } catch {
        return; // heartbeat / non-JSON comment frame
      }
      switch (frame.type) {
        case "log":
          if (typeof frame.data === "string") setProgressLine(frame.data);
          break;
        case "error":
          finish();
          toast.error(t("toast_failed_title"), {
            description:
              typeof frame.data === "string" ? frame.data : t("toast_unknown_error"),
          });
          break;
        case "done":
          handleDone((frame.data ?? {}) as ContinueDoneData);
          break;
        default:
          break; // "session" / "stream" frames need no handling here
      }
    },
    [finish, handleDone, t],
  );

  usePostStream({
    url: pendingBody ? CONTINUE_LIBRARY_URL : null,
    body: pendingBody,
    onMessage: handleMessage,
    onError: (err) => {
      finish();
      toast.error(t("toast_failed_title"), {
        description: err instanceof Error ? err.message : String(err),
      });
    },
    onClose: () => {
      // Server closed without a terminal frame — don't strand the UI in "writing".
      if (settledRef.current) return;
      finish();
      toast.error(t("toast_failed_title"), {
        description: t("toast_stream_closed"),
      });
    },
  });

  const handlePreviewOutlines = React.useCallback(async () => {
    if (!story || isWriting || isPlanning) return;
    setIsPlanning(true);
    try {
      const res = await fetchContinueOutlines(story, {
        additionalChapters: chapterCount,
        direction,
      });
      if (!res.outlines?.length) {
        toast.error(t("toast_outline_failed"), {
          description: t("toast_outline_empty"),
        });
        return;
      }
      setPlan({ key: planKey, outlines: res.outlines });
      if (res.note) toast.info(res.note);
    } catch (err) {
      toast.error(t("toast_outline_failed"), {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsPlanning(false);
    }
  }, [chapterCount, direction, isPlanning, isWriting, planKey, story, t]);

  const updateOutline = React.useCallback(
    (index: number, patch: Partial<ContinuationOutline>) => {
      setPlan((prev) =>
        prev
          ? {
              ...prev,
              outlines: prev.outlines.map((o, i) =>
                i === index ? { ...o, ...patch } : o,
              ),
            }
          : prev,
      );
    },
    [],
  );

  const handleWrite = React.useCallback(() => {
    if (!story || isWriting) return;
    settledRef.current = false;
    setIsWriting(true);
    setWritten(0);
    setProgressLine(t("writing_stage_default"));
    setPendingBody(
      buildContinueBody(story, {
        additionalChapters: chapterCount,
        direction,
        wordCount: effectiveWordCount,
        outlines: outlines ?? [],
      }),
    );
  }, [chapterCount, direction, effectiveWordCount, isWriting, outlines, story, t]);

  if (!hydrated) {
    return (
      <div className="rounded-xl border border-border/60 bg-card p-5 text-sm text-muted-foreground">
        {t("loading_library")}
      </div>
    );
  }

  if (stories.length === 0) {
    return (
      <div className="rounded-xl border border-border/60 bg-card p-5 text-sm text-muted-foreground">
        {t("no_stories")}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
        </div>
        <Button type="button" variant="outline" onClick={() => router.push("/library/")}>
          <ArrowLeft className="size-4" aria-hidden />
          {t("back_to_library")}
        </Button>
      </div>

      <section className="rounded-xl border border-border/60 bg-card/70 p-5 shadow-sm">
        <div className="grid gap-4 md:grid-cols-[1fr_180px_180px]">
          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>{t("label_story")}</span>
            <select
              value={storyId}
              onChange={(e) => {
                setStoryId(e.target.value);
                selectStory(e.target.value);
              }}
              disabled={isWriting}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {stories.map((s) => (
                <option key={s.id} value={s.id}>
                  {t("story_option", {
                    title: displayStoryTitle(s, t("untitled_story")),
                    count: s.chapters.length,
                  })}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>
              {remaining != null
                ? t("label_batch_count_with_remaining", {
                    remaining,
                    target: target ?? 0,
                  })
                : t("label_batch_count")}
            </span>
            <input
              type="number"
              min={1}
              max={maxBatch}
              value={chapterCount}
              onChange={(e) =>
                setChapterCount(
                  Math.max(1, Math.min(maxBatch, Number(e.target.value) || 1)),
                )
              }
              disabled={isWriting || atTarget}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
          </label>

          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>{t("label_word_count")}</span>
            <input
              type="number"
              min={MIN_WORD_COUNT}
              max={MAX_WORD_COUNT}
              step={100}
              value={effectiveWordCount}
              onChange={(e) => setWordCountOverride(clampWordCount(Number(e.target.value)))}
              disabled={isWriting || atTarget}
              aria-label={t("label_word_count")}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            />
            <span className="block text-xs font-normal text-muted-foreground">
              {wordCountOverride == null
                ? t("word_count_auto", { value: suggestedWordCount })
                : t("word_count_manual")}
            </span>
          </label>
        </div>

        {target != null ? (
          <div className="mt-4 rounded-lg border border-border/40 bg-background/40 p-3 text-xs">
            <div className="flex items-center justify-between text-muted-foreground">
              <span>{t("progress_label")}</span>
              <span className="font-medium text-foreground">
                {t("progress_value", { written: writtenCount, target })}
                {atTarget ? t("progress_done_suffix") : ""}
              </span>
            </div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-border/60">
              <div
                className="h-full bg-primary transition-all"
                style={{
                  width: `${Math.min(100, Math.round((writtenCount / Math.max(1, target)) * 100))}%`,
                }}
              />
            </div>
            {atTarget ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={isWriting}
                  onClick={() => {
                    if (!story) return;
                    updateStory(story.id, { targetChapters: target + 5 });
                    toast.success(t("epilogue_extra_done"));
                  }}
                >
                  {t("epilogue_extra")}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={isWriting}
                  onClick={() => {
                    if (!story) return;
                    updateStory(story.id, { targetChapters: target + 10 });
                    toast.success(t("epilogue_extend_done"));
                  }}
                >
                  {t("epilogue_extend")}
                </Button>
              </div>
            ) : null}
          </div>
        ) : story ? (
          <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-xs">
            <p className="font-medium text-foreground">{t("no_target_title")}</p>
            <p className="mt-1 text-muted-foreground">{t("no_target_hint")}</p>
            <LegacyTargetInline
              defaultValue={getChapterDefault(story.genre ?? "")}
              min={getChapterRange(story.genre ?? "").min}
              max={getChapterRange(story.genre ?? "").max}
              unitLabel={t("chapters_unit")}
              applyLabel={t("set_target_button")}
              onApply={(value) => {
                updateStory(story.id, { targetChapters: value });
                toast.success(t("set_target_done", { value }));
              }}
              disabled={isWriting}
            />
          </div>
        ) : null}

        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_280px]">
          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>{t("label_direction")}</span>
            <Textarea
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              maxLength={MAX_DIRECTION_LEN}
              disabled={isWriting}
              className="min-h-36"
              placeholder={t("direction_placeholder")}
            />
            <span className="block text-xs text-muted-foreground">
              {t("direction_counter", { length: direction.length })}
            </span>
          </label>

          <div className="rounded-lg border border-border/60 bg-background/45 p-4 text-sm">
            <div className="mb-3 flex items-center gap-2 font-medium text-foreground">
              <BookOpen className="size-4" aria-hidden />
              {t("context_used_title")}
            </div>
            <ul className="space-y-2 text-muted-foreground">
              <li>• {t("context_used_1")}</li>
              <li>• {t("context_used_2")}</li>
              <li>• {t("context_used_3")}</li>
              <li>• {t("context_used_4")}</li>
              <li>• {t("context_used_5")}</li>
            </ul>
          </div>
        </div>

        {outlines ? (
          <div className="mt-4 rounded-lg border border-border/60 bg-background/45 p-4">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2 text-sm font-medium text-foreground">
                <ListChecks className="size-4" aria-hidden />
                {t("outline_title", { count: outlines.length })}
              </div>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={isWriting || isPlanning}
                onClick={() => setPlan(null)}
              >
                {t("outline_discard")}
              </Button>
            </div>
            <p className="mb-3 text-xs text-muted-foreground">{t("outline_hint")}</p>
            <ol className="space-y-3">
              {outlines.map((o, i) => (
                <li
                  key={o.chapter_number ?? i}
                  className="rounded-md border border-border/40 bg-card/40 p-3"
                >
                  <div className="mb-2 flex items-center gap-2">
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {t("outline_chapter", { number: o.chapter_number ?? i + 1 })}
                    </span>
                    <input
                      type="text"
                      value={o.title ?? ""}
                      onChange={(e) => updateOutline(i, { title: e.target.value })}
                      disabled={isWriting}
                      aria-label={t("outline_title_field")}
                      className="h-8 w-full rounded-md border border-input bg-background px-2 text-sm font-medium text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                    />
                  </div>
                  <Textarea
                    value={o.summary ?? ""}
                    onChange={(e) => updateOutline(i, { summary: e.target.value })}
                    disabled={isWriting}
                    aria-label={t("outline_summary_field")}
                    className="min-h-20 text-sm"
                  />
                </li>
              ))}
            </ol>
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground" aria-live="polite">
            {isWriting
              ? progressLine || t("writing_stage_default")
              : isPlanning
                ? t("outline_planning")
                : written > 0
                  ? t("writing_done", { written })
                  : t("completion_hint")}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => void handlePreviewOutlines()}
              disabled={!story || isWriting || isPlanning || atTarget}
            >
              <ListChecks className="size-4" aria-hidden />
              {isPlanning
                ? t("btn_planning")
                : outlines
                  ? t("btn_replan")
                  : t("btn_preview_outline")}
            </Button>
            <Button
              type="button"
              onClick={handleWrite}
              disabled={!story || isWriting || isPlanning || atTarget}
            >
              <Sparkles className="size-4" aria-hidden />
              {isWriting
                ? t("btn_writing")
                : atTarget
                  ? t("btn_at_target")
                  : outlines
                    ? t("btn_write_approved", { count: outlines.length })
                    : t("btn_write_n", { count: chapterCount })}
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}

function LegacyTargetInline({
  defaultValue,
  min,
  max,
  onApply,
  disabled,
  unitLabel,
  applyLabel,
}: {
  defaultValue: number;
  min: number;
  max: number;
  onApply: (value: number) => void;
  disabled?: boolean;
  unitLabel: string;
  applyLabel: string;
}) {
  const [val, setVal] = React.useState(defaultValue);
  React.useEffect(() => {
    setVal(defaultValue);
  }, [defaultValue]);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <input
        type="number"
        min={min}
        max={max}
        value={val}
        onChange={(e) =>
          setVal(
            Math.max(
              min,
              Math.min(max, Number(e.target.value) || defaultValue),
            ),
          )
        }
        disabled={disabled}
        className="h-8 w-20 rounded-md border border-input bg-background px-2 text-xs text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <span className="text-muted-foreground">{unitLabel}</span>
      <Button
        type="button"
        size="sm"
        variant="outline"
        disabled={disabled}
        onClick={() => onApply(val)}
      >
        {applyLabel}
      </Button>
    </div>
  );
}
