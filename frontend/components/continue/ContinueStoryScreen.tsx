"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, BookOpen, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { rehydrateLibrary, useLibraryStore } from "@/stores/library-store";
import { forgeFromSentenceStream } from "@/lib/api/forge";
import type { StoryChapter } from "@/types/story";
import { displayStoryTitle } from "@/lib/library/display-helpers";
import { getChapterDefault, getChapterRange } from "@/lib/library/chapter-defaults";

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
  const [isWriting, setIsWriting] = React.useState(false);
  const [stage, setStage] = React.useState<string | null>(null);
  const [written, setWritten] = React.useState(0);

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

  React.useEffect(() => {
    if (chapterCount > maxBatch) setChapterCount(maxBatch);
  }, [chapterCount, maxBatch]);

  const buildIdea = React.useCallback(
    (chapterNumber: number) => {
      if (!story) return "";
      const lastChapter = story.chapters.at(-1);
      const characters = story.characters.map((c) => c.name).filter(Boolean).slice(0, 8).join(", ");
      const automaticDirection =
        "Không có chỉ đạo riêng: hãy tự nối tiếp từ chương cuối, giữ đúng thể loại, tông giọng, nhân vật và mở thêm cao trào hợp lý.";
      const isFinal = target != null && chapterNumber >= target;
      const targetLine =
        target != null
          ? isFinal
            ? `Đây là CHƯƠNG CUỐI (Chương ${chapterNumber}/${target}) — bắt buộc khép trọn vẹn cốt truyện, giải quyết mâu thuẫn chính và đóng arc nhân vật. KHÔNG để cliffhanger, KHÔNG mở mạch mới.`
            : `Chương ${chapterNumber}/${target} — còn ${target - chapterNumber} chương trước khi truyện phải kết thúc, hãy điều tiết nhịp độ phù hợp.`
          : `Đây là chương viết tiếp số ${chapterNumber}.`;
      return [
        `Viết tiếp truyện "${story.title}".`,
        story.genre ? `Thể loại: ${story.genre}.` : "",
        story.tone ? `Tông giọng: ${story.tone}.` : "",
        story.description ? `Tóm tắt truyện: ${story.description}` : "",
        characters ? `Nhân vật chính/phụ đã biết: ${characters}.` : "",
        lastChapter
          ? `Chương gần nhất: ${lastChapter.title}. ${lastChapter.summary || lastChapter.content.slice(0, 220)}`
          : "Truyện chưa có chương; hãy viết chương mở đầu phù hợp với tiền đề.",
        targetLine,
        direction.trim() ? `Chỉ đạo của người dùng: ${direction.trim()}` : automaticDirection,
      ]
        .filter(Boolean)
        .join(" ")
        .slice(0, 700);
    },
    [direction, story, target],
  );

  const stageLabel = React.useCallback(
    (s: string | null) => {
      switch (s) {
        case "planning":
          return t("writing_stage_planning");
        case "characters":
          return t("writing_stage_characters");
        case "chapter":
          return t("writing_stage_chapter");
        case "choices":
          return t("writing_stage_choices");
        default:
          return t("writing_stage_default");
      }
    },
    [t],
  );

  const handleWrite = React.useCallback(async () => {
    if (!story || isWriting) return;
    setIsWriting(true);
    setWritten(0);
    try {
      for (let i = 0; i < chapterCount; i += 1) {
        setStage("planning");
        const result = await forgeFromSentenceStream(
          { sentenceIdea: buildIdea(story.chapters.length + i + 1) },
          { onStage: (nextStage) => setStage(nextStage) },
        );
        const now = new Date().toISOString();
        const chapter: StoryChapter = {
          id: `chapter-${Date.now().toString(36)}-${i}`,
          title: result.firstChapter.title || `Chương ${story.chapters.length + i + 1}`,
          content: result.firstChapter.content,
          summary: result.firstChapter.summary,
          badge: "Ch",
          status: "ready",
          images: [],
          createdAt: now,
        };
        appendChapter(story.id, chapter);
        setWritten(i + 1);
      }
      toast.success(t("toast_success_title"), {
        description: t("toast_success_body", { count: chapterCount }),
      });
      router.push(`/reader/?id=${encodeURIComponent(story.id)}`);
    } catch (err) {
      toast.error(t("toast_failed_title"), {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsWriting(false);
      setStage(null);
    }
  }, [appendChapter, buildIdea, chapterCount, isWriting, router, story, t]);

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
        <div className="grid gap-4 md:grid-cols-[1fr_180px]">
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
              maxLength={500}
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

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {isWriting
              ? t("writing_progress", {
                  stage: stageLabel(stage),
                  written,
                  total: chapterCount,
                })
              : t("completion_hint")}
          </p>
          <Button
            type="button"
            onClick={() => void handleWrite()}
            disabled={!story || isWriting || atTarget}
          >
            <Sparkles className="size-4" aria-hidden />
            {isWriting
              ? t("btn_writing")
              : atTarget
                ? t("btn_at_target")
                : t("btn_write_n", { count: chapterCount })}
          </Button>
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
