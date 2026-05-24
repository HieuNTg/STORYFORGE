"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { BookOpen } from "lucide-react";

import { ChapterReader } from "@/components/reader/ChapterReader";
import { ReaderControls } from "@/components/reader/ReaderControls";
import {
  rehydrateLibrary,
  useLibraryStore,
} from "@/stores/library-store";
import {
  columnFromUi,
  columnToUi,
  useReaderStore,
  type ReaderColumnUi,
} from "@/stores/reader-store";

export function ReaderStartScreen() {
  const searchParams = useSearchParams();
  const queryId = searchParams?.get("id") ?? null;
  const stories = useLibraryStore((s) => s.stories);
  const selectedId = useLibraryStore((s) => s.selectedId);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const [storyId, setStoryId] = React.useState("");
  const [chapterIdx, setChapterIdx] = React.useState(0);

  const hydrateReader = useReaderStore((s) => s.hydrate);
  React.useEffect(() => {
    rehydrateLibrary();
    hydrateReader();
  }, [hydrateReader]);

  React.useEffect(() => {
    if (queryId && stories.some((s) => s.id === queryId)) {
      if (storyId !== queryId) setStoryId(queryId);
      return;
    }
    if (!storyId && selectedId && stories.some((s) => s.id === selectedId)) {
      setStoryId(selectedId);
      return;
    }
    if (!storyId && stories.length > 0) setStoryId(stories[0].id);
  }, [queryId, selectedId, stories, storyId]);

  const selectedStory = React.useMemo(
    () => stories.find((s) => s.id === storyId) ?? null,
    [stories, storyId],
  );

  React.useEffect(() => {
    setChapterIdx(0);
  }, [selectedStory?.id]);

  const chapters = selectedStory?.chapters ?? [];
  const safeIdx = chapters.length === 0 ? 0 : Math.max(0, Math.min(chapterIdx, chapters.length - 1));
  const currentChapter = chapters[safeIdx];

  const fontSize = useReaderStore((s) => s.fontSize);
  const lineHeight = useReaderStore((s) => s.lineHeight);
  const fontFamily = useReaderStore((s) => s.fontFamily);
  const column = useReaderStore((s) => s.column);
  const setFontSize = useReaderStore((s) => s.setFontSize);
  const setLineHeight = useReaderStore((s) => s.setLineHeight);
  const setFontFamily = useReaderStore((s) => s.setFontFamily);
  const setColumn = useReaderStore((s) => s.setColumn);
  const cycleTheme = useReaderStore((s) => s.cycleTheme);
  const theme = useReaderStore((s) => s.theme);

  const columnUi: ReaderColumnUi = columnToUi(column);
  const fontUi = fontFamily === "serif" ? "serif" : "sans";

  if (!hydrated) {
    return <div className="rounded-lg border border-border/70 bg-card p-5 text-sm text-muted-foreground">Đang tải kho truyện…</div>;
  }

  if (stories.length === 0) {
    return (
      <div className="rounded-lg border border-border/70 bg-card p-5">
        <div className="flex items-start gap-3">
          <BookOpen className="mt-0.5 size-5 text-[var(--accent-strong)]" aria-hidden="true" />
          <div>
            <h2 className="text-lg font-medium text-foreground">Chưa có truyện để đọc</h2>
            <p className="mt-1 text-sm text-muted-foreground">Tạo hoặc nhập một bộ truyện trong Thư viện trước.</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-border/70 bg-card p-5 shadow-sm">
        <div className="mb-5 flex items-start gap-3">
          <span className="rounded-md border border-[var(--accent)]/30 bg-[color-mix(in_oklab,var(--accent)_10%,transparent)] p-2 text-[var(--accent-strong)]">
            <BookOpen className="size-5" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-lg font-medium text-foreground">Chọn truyện để đọc</h2>
            <p className="mt-1 text-sm text-muted-foreground">Chọn bộ truyện và chương trong thư viện local.</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>Bộ truyện</span>
            <select
              value={storyId}
              onChange={(e) => setStoryId(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {stories.map((story) => (
                <option key={story.id} value={story.id}>
                  {story.title} · {story.chapters.length} chương
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>Chương</span>
            <select
              value={safeIdx}
              onChange={(e) => setChapterIdx(Number(e.target.value))}
              disabled={chapters.length === 0}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {chapters.length === 0 ? (
                <option value={0}>Truyện chưa có chương</option>
              ) : (
                chapters.map((chapter, idx) => (
                  <option key={chapter.id} value={idx}>
                    {chapter.title || `Chương ${idx + 1}`}
                  </option>
                ))
              )}
            </select>
          </label>
        </div>
      </section>

      {currentChapter ? (
        <section
          className="rounded-lg border border-border/70 bg-card p-5 shadow-sm"
          style={{ maxWidth: columnUi === "narrow" ? 720 : columnUi === "wide" ? 1040 : 860 }}
        >
          <div className="mb-4 flex justify-end">
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
          <ChapterReader
            title={currentChapter.title}
            content={currentChapter.content}
            fontSize={fontSize}
            lineHeight={lineHeight}
            fontFamily={fontUi}
          />
        </section>
      ) : (
        <div className="rounded-lg border border-border/70 bg-card p-5 text-sm text-muted-foreground">
          Truyện này chưa có chương để đọc.
        </div>
      )}
    </div>
  );
}
