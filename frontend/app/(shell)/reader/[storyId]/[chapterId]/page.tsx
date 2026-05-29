"use client";

/**
 * Reader route — `/reader/{storyId}/{chapterId}` — cinematic reader chrome
 * with IllustrationBanner + ChapterReader + PipelineOverlay.
 *
 * Differs from `/library/[id]?chapter=N`:
 *   - chapterId in URL path (deep-linkable 1-based chapter number)
 *   - IllustrationBanner above the prose (when enable_chapter_illustration)
 *   - Regenerate button wired to POST /api/images/{sid}/generate with chapter_id
 *   - PipelineOverlay reveals SSE-style progress for image regen
 *
 * Both flags come from `/api/config`. When off, banner + overlay are hidden
 * and the route degrades to a plain reader.
 */

import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { ReaderShell } from "@/components/reader/ReaderShell";
import { ChapterList } from "@/components/reader/ChapterList";
import {
  ChapterReader,
  type ReaderFontFamily as ReaderFontUi,
} from "@/components/reader/ChapterReader";
import { ReaderControls } from "@/components/reader/ReaderControls";
import { BookmarkButton } from "@/components/reader/BookmarkButton";
import { IllustrationBanner } from "@/components/reader/IllustrationBanner";
import { ComicPanels } from "@/components/reader/ComicPanels";
import { PipelineOverlay } from "@/components/pipeline/PipelineOverlay";
import type { PipelineLogLine } from "@/components/pipeline/PipelineLogTerminal";
import { useStory, useConfig, type StoryChapter } from "@/lib/api/queries";
import { generateChapterImage } from "@/lib/api/illustration";
import {
  useReaderStore,
  columnToUi,
  columnFromUi,
  type ReaderColumnUi,
} from "@/stores/reader-store";

interface ChapterWithImages extends StoryChapter {
  /** Legacy field name kept for back-compat with older payloads. */
  image_paths?: string[];
}

function pickChapterImages(c?: StoryChapter): string[] {
  if (!c) return [];
  const withImg = c as ChapterWithImages;
  return withImg.images ?? withImg.image_paths ?? [];
}

function nowTs(): string {
  return new Date().toLocaleTimeString("vi-VN", { hour12: false });
}

export default function ReaderPage() {
  const params = useParams<{ storyId: string; chapterId: string }>();
  const router = useRouter();
  const storyId = params?.storyId ?? null;
  const chapterParam = params?.chapterId ?? "1";
  const chapterNumber = Math.max(1, Number.parseInt(chapterParam, 10) || 1);

  const { data, isLoading, error, refetch } = useStory(storyId);
  const cfg = useConfig();
  const illustrationEnabled = !!cfg.data?.pipeline.enable_chapter_illustration;
  const overlayEnabled = !!cfg.data?.pipeline.enable_pipeline_overlay;

  const hydrate = useReaderStore((s) => s.hydrate);
  React.useEffect(() => {
    hydrate();
  }, [hydrate]);

  const fontSize = useReaderStore((s) => s.fontSize);
  const lineHeight = useReaderStore((s) => s.lineHeight);
  const fontFamily = useReaderStore((s) => s.fontFamily);
  const theme = useReaderStore((s) => s.theme);
  const column = useReaderStore((s) => s.column);
  const bookmarks = useReaderStore((s) => s.bookmarks);
  const setFontSize = useReaderStore((s) => s.setFontSize);
  const setLineHeight = useReaderStore((s) => s.setLineHeight);
  const setFontFamily = useReaderStore((s) => s.setFontFamily);
  const setColumn = useReaderStore((s) => s.setColumn);
  const cycleTheme = useReaderStore((s) => s.cycleTheme);
  const saveBookmark = useReaderStore((s) => s.saveBookmark);
  const clearBookmark = useReaderStore((s) => s.clearBookmark);

  const fontUi: ReaderFontUi = fontFamily === "serif" ? "serif" : "sans";

  const chapters: StoryChapter[] = React.useMemo(() => {
    if (!data) return [];
    return data.chapters ?? data.draft?.chapters ?? [];
  }, [data]);

  const safeIdx =
    chapters.length === 0
      ? 0
      : Math.max(0, Math.min(chapterNumber - 1, chapters.length - 1));
  const currentChapter = chapters[safeIdx];
  const chapterImages = pickChapterImages(currentChapter);

  const chapterListItems = React.useMemo(
    () =>
      chapters.map((c, idx) => ({
        id: String(c.number ?? idx + 1),
        title: c.title ?? `Chương ${idx + 1}`,
        word_count: c.word_count,
      })),
    [chapters],
  );

  const columnUi: ReaderColumnUi = columnToUi(column);

  const storyKey = storyId ?? "";
  const isBookmarked =
    !!bookmarks[storyKey] && bookmarks[storyKey]?.chapter === safeIdx;
  const [bookmarkBusy, setBookmarkBusy] = React.useState(false);

  const handleToggleBookmark = React.useCallback(() => {
    if (!storyKey) return;
    setBookmarkBusy(true);
    try {
      if (isBookmarked) {
        clearBookmark(storyKey);
        toast.success("Đã bỏ đánh dấu");
      } else {
        saveBookmark(storyKey, safeIdx);
        toast.success("Đã đánh dấu chương");
      }
    } finally {
      setBookmarkBusy(false);
    }
  }, [storyKey, isBookmarked, clearBookmark, saveBookmark, safeIdx]);

  const handleSelectChapter = React.useCallback(
    (idx: number) => {
      if (!storyId) return;
      const next = idx + 1;
      router.push(`/reader/${storyId}/${next}`);
    },
    [storyId, router],
  );

  // ---- Illustration regen --------------------------------------------------
  const [overlayOpen, setOverlayOpen] = React.useState(false);
  const [stageIdx, setStageIdx] = React.useState(0);
  const [stageProgress, setStageProgress] = React.useState(0);
  const [log, setLog] = React.useState<PipelineLogLine[]>([]);
  const [regenLoading, setRegenLoading] = React.useState(false);

  const pushLog = React.useCallback((line: PipelineLogLine) => {
    setLog((prev) => [...prev, line]);
  }, []);

  const handleRegenerate = React.useCallback(async () => {
    if (!storyId || !illustrationEnabled || regenLoading) return;
    setRegenLoading(true);
    setOverlayOpen(overlayEnabled);
    setLog([]);
    setStageIdx(0);
    setStageProgress(10);
    pushLog({
      ts: nowTs(),
      stage: "🔍",
      text: `Phân tích chương ${chapterNumber}`,
      level: "info",
    });
    try {
      setStageIdx(1);
      setStageProgress(40);
      pushLog({
        ts: nowTs(),
        stage: "✍️",
        text: "Yêu cầu nhà cung cấp ảnh",
        level: "info",
      });
      const result = await generateChapterImage(storyId, chapterNumber);
      setStageIdx(2);
      setStageProgress(75);
      pushLog({
        ts: nowTs(),
        stage: "📡",
        text: `Nhận ${result.count} ảnh`,
        level: "info",
      });
      setStageIdx(3);
      setStageProgress(100);
      pushLog({
        ts: nowTs(),
        stage: "✓",
        text: "Hoàn tất minh hoạ",
        level: "success",
      });
      await refetch();
      toast.success("Đã sinh minh hoạ");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      pushLog({ ts: nowTs(), stage: "⚠", text: msg, level: "error" });
      toast.error(`Không thể sinh minh hoạ: ${msg}`);
    } finally {
      setRegenLoading(false);
    }
  }, [
    storyId,
    illustrationEnabled,
    regenLoading,
    overlayEnabled,
    chapterNumber,
    pushLog,
    refetch,
  ]);

  // ---- Render --------------------------------------------------------------

  if (!storyId) {
    return (
      <div className="text-sm text-muted-foreground">Không tìm thấy truyện.</div>
    );
  }
  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Đang tải truyện…</div>;
  }
  if (error) {
    return (
      <div className="text-sm text-destructive">
        Lỗi tải truyện: {error.message}
      </div>
    );
  }
  if (chapters.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">Truyện chưa có chương.</div>
    );
  }

  const proseNode = (
    <div className="flex flex-col gap-4">
      {illustrationEnabled ? (
        chapterImages.length > 0 ? (
          <ComicPanels
            images={chapterImages}
            alt={`Minh hoạ chương ${chapterNumber}: ${currentChapter?.title ?? ""}`}
            loading={regenLoading}
            onRegenerate={handleRegenerate}
          />
        ) : (
          <IllustrationBanner
            src={undefined}
            alt={`Minh hoạ chương ${chapterNumber}: ${currentChapter?.title ?? ""}`}
            loading={regenLoading}
            onRegenerate={handleRegenerate}
          />
        )
      ) : null}
      <ChapterReader
        title={currentChapter?.title}
        content={currentChapter?.content ?? ""}
        fontSize={fontSize}
        lineHeight={lineHeight}
        fontFamily={fontUi}
      />
    </div>
  );

  return (
    <>
      <ReaderShell
        theme={theme}
        columnWidth={columnUi}
        chapterList={
          <ChapterList
            chapters={chapterListItems}
            currentChapter={safeIdx}
            onSelect={handleSelectChapter}
          />
        }
        controls={
          <div className="flex items-center gap-1.5">
            <BookmarkButton
              isBookmarked={isBookmarked}
              onToggle={handleToggleBookmark}
              loading={bookmarkBusy}
            />
            <ReaderControls
              fontSize={fontSize}
              onFontSize={setFontSize}
              lineHeight={lineHeight}
              onLineHeight={setLineHeight}
              fontFamily={fontUi}
              onFontFamily={setFontFamily}
              theme={theme}
              onCycleTheme={cycleTheme}
              columnWidth={columnUi}
              onColumnWidth={(w) => setColumn(columnFromUi(w))}
            />
          </div>
        }
        prose={proseNode}
      />
      {overlayEnabled ? (
        <PipelineOverlay
          open={overlayOpen}
          onOpenChange={setOverlayOpen}
          currentStageIdx={stageIdx}
          stageProgress={stageProgress}
          log={log}
          title="Đang sinh minh hoạ"
          description={`Chương ${chapterNumber}${currentChapter?.title ? ` — ${currentChapter.title}` : ""}`}
        />
      ) : null}
    </>
  );
}
