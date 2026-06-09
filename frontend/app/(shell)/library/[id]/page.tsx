"use client";

/**
 * Reader page — composes Designer's ReaderShell + ChapterList + ChapterReader
 * + ReaderControls + BookmarkButton with `useStory` + nuqs `?chapter=`.
 *
 * Persisted prefs come from `reader-store` (which mirrors legacy
 * `forge_reader_*` localStorage keys for cutover parity — R2.2).
 */

import * as React from "react";
import { useParams } from "next/navigation";
import { useQueryState, parseAsInteger } from "nuqs";
import { toast } from "sonner";
import { ReaderShell } from "@/components/reader/ReaderShell";
import { ChapterList } from "@/components/reader/ChapterList";
import { ChapterReader, type ReaderFontFamily as ReaderFontUi } from "@/components/reader/ChapterReader";
import { ReaderControls } from "@/components/reader/ReaderControls";
import { BookmarkButton } from "@/components/reader/BookmarkButton";
import { ComicGenerator } from "@/components/reader/ComicGenerator";
import { useStory, type StoryChapter } from "@/lib/api/queries";
import {
  useReaderStore,
  columnToUi,
  columnFromUi,
  type ReaderColumnUi,
} from "@/stores/reader-store";

export default function LibraryDetailPage() {
  const params = useParams<{ id: string }>();
  const storyId = params?.id ?? null;

  const { data, isLoading, error } = useStory(storyId);

  // Hydrate persisted reader prefs on first client render (SSR-safe).
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

  const [chapterIdx, setChapterIdx] = useQueryState(
    "chapter",
    parseAsInteger.withDefault(0)
  );

  // Reader font UI is sans|serif; store can hold "mono" too — coerce.
  const fontUi: ReaderFontUi = fontFamily === "serif" ? "serif" : "sans";

  // Chapters — backend embeds them under either `chapters` or `draft.chapters`.
  const chapters: StoryChapter[] = React.useMemo(() => {
    if (!data) return [];
    return data.chapters ?? data.draft?.chapters ?? [];
  }, [data]);

  const safeIdx = chapters.length === 0 ? 0 : Math.max(0, Math.min(chapterIdx ?? 0, chapters.length - 1));
  const currentChapter = chapters[safeIdx];

  // Bookmark state for the current story.
  const storyKey = storyId ?? "";
  const isBookmarked = !!bookmarks[storyKey] && bookmarks[storyKey]?.chapter === safeIdx;
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

  // Restore bookmark on first load — only when ?chapter is at default 0 and
  // a saved bookmark exists.
  const restoredRef = React.useRef(false);
  React.useEffect(() => {
    if (restoredRef.current) return;
    if (!storyKey || chapters.length === 0) return;
    const bm = bookmarks[storyKey];
    if (bm && (chapterIdx ?? 0) === 0 && bm.chapter > 0 && bm.chapter < chapters.length) {
      void setChapterIdx(bm.chapter);
    }
    restoredRef.current = true;
  }, [storyKey, chapters.length, bookmarks, chapterIdx, setChapterIdx]);

  const chapterListItems = React.useMemo(
    () =>
      chapters.map((c, idx) => ({
        id: String(c.number ?? idx + 1),
        title: c.title ?? `Chương ${idx + 1}`,
        word_count: c.word_count,
      })),
    [chapters]
  );

  const columnUi: ReaderColumnUi = columnToUi(column);

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

  return (
    <ReaderShell
      theme={theme}
      columnWidth={columnUi}
      chapterList={
        <div className="flex flex-col gap-4">
          <ChapterList
            chapters={chapterListItems}
            currentChapter={safeIdx}
            onSelect={(idx) => void setChapterIdx(idx)}
          />
          <ComicGenerator sessionId={storyId} />
        </div>
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
      prose={
        <ChapterReader
          title={currentChapter?.title}
          content={currentChapter?.content ?? ""}
          fontSize={fontSize}
          lineHeight={lineHeight}
          fontFamily={fontUi}
        />
      }
    />
  );
}
