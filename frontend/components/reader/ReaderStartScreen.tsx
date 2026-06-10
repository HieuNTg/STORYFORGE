"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
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
import { displayStoryTitle } from "@/lib/library/display-helpers";


export function ReaderStartScreen() {
  const searchParams = useSearchParams();
  const queryId = searchParams?.get("id") ?? null;
  const queryChapter = searchParams?.get("chapter") ?? null;
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

  // Deep link from the Library's "Có tranh" rows: /reader/?id=...&chapter=N
  // (1-based). Declared AFTER the reset effect so it wins on story change.
  React.useEffect(() => {
    if (!queryChapter || !selectedStory) return;
    const n = Number(queryChapter);
    if (!Number.isInteger(n)) return;
    if (n >= 1 && n <= selectedStory.chapters.length) setChapterIdx(n - 1);
  }, [queryChapter, selectedStory]);

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

  const t = useTranslations("reader");
  const tLib = useTranslations("library");

  if (!hydrated) {
    return <div className="rounded-lg border border-border/70 bg-card p-5 text-sm text-muted-foreground">{t("loading")}</div>;
  }

  if (stories.length === 0) {
    return (
      <div className="rounded-lg border border-border/70 bg-card p-5">
        <div className="flex items-start gap-3">
          <BookOpen className="mt-0.5 size-5 text-[var(--accent-strong)]" aria-hidden="true" />
          <div>
            <h2 className="text-lg font-medium text-foreground">{t("empty")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("empty_hint")}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex flex-col items-center space-y-6" style={{ maxWidth: columnUi === "narrow" ? 720 : columnUi === "wide" ? 1040 : 860 }}>
      <section className="w-full rounded-lg border border-border/70 bg-card p-5 shadow-sm">
        <div className="mb-5 flex items-start gap-3">
          <span className="rounded-md border border-[var(--accent)]/30 bg-[color-mix(in_oklab,var(--accent)_10%,transparent)] p-2 text-[var(--accent-strong)]">
            <BookOpen className="size-5" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-lg font-medium text-foreground">{t("select_story_title")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{t("select_story_hint")}</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>{t("select_story")}</span>
            <select
              value={storyId}
              onChange={(e) => setStoryId(e.target.value)}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              {stories.map((story) => (
                <option key={story.id} value={story.id}>
                  {displayStoryTitle(story, tLib("untitled_story"))} · {t("chapters_count", { count: story.chapters.length })}
                </option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>{t("select_chapter")}</span>
            <select
              value={safeIdx}
              onChange={(e) => setChapterIdx(Number(e.target.value))}
              disabled={chapters.length === 0}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {chapters.length === 0 ? (
                <option value={0}>{t("no_chapters_option")}</option>
              ) : (
                chapters.map((chapter, idx) => (
                  <option key={chapter.id} value={idx}>
                    {chapter.title || `${t("select_chapter")} ${idx + 1}`}
                  </option>
                ))
              )}
            </select>
          </label>
        </div>
      </section>

      {currentChapter ? (
        <section className="w-full rounded-lg border border-border/70 bg-card p-5 shadow-sm">
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
          {/* Prose only — comics live in the Gallery (Bộ sưu tập), the Reader
              is for novels (CEO call 2026-06-10). */}
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
          {t("no_chapters")}
        </div>
      )}
    </div>
  );
}
