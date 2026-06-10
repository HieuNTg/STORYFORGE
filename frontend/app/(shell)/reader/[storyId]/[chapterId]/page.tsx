"use client";

/**
 * Reader route — `/reader/{storyId}/{chapterId}` — cinematic reader chrome,
 * prose only. Comics live in the Gallery (Bộ sưu tập), the Reader is for
 * novels (CEO call 2026-06-10).
 *
 * Differs from `/library/[id]?chapter=N`: chapterId in URL path
 * (deep-linkable 1-based chapter number).
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
import { useStory, type StoryChapter } from "@/lib/api/queries";
import {
  useReaderStore,
  columnToUi,
  columnFromUi,
  type ReaderColumnUi,
} from "@/stores/reader-store";

export default function ReaderPage() {
  const params = useParams<{ storyId: string; chapterId: string }>();
  const router = useRouter();
  const storyId = params?.storyId ?? null;
  const chapterParam = params?.chapterId ?? "1";
  const chapterNumber = Math.max(1, Number.parseInt(chapterParam, 10) || 1);

  const { data, isLoading, error } = useStory(storyId);

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
    <ChapterReader
      title={currentChapter?.title}
      content={currentChapter?.content ?? ""}
      fontSize={fontSize}
      lineHeight={lineHeight}
      fontFamily={fontUi}
    />
  );

  return (
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
  );
}
