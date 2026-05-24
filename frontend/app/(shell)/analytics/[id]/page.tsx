"use client";

/**
 * Analytics page — composes Designer's QualityCard + WordCountCard +
 * ChapterChart + EventTimeline. Code-splits CharacterGraph behind ?show=characters.
 *
 * Data: `useStoryAnalytics(id)` derives stats from the same checkpoint payload
 * `useStory` already returns — see `lib/api/queries.ts`. No extra endpoint.
 */

import * as React from "react";
import dynamic from "next/dynamic";
import { useParams } from "next/navigation";
import { useQueryState } from "nuqs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { QualityCard } from "@/components/analytics/QualityCard";
import { WordCountCard } from "@/components/analytics/WordCountCard";
import { ChapterChart } from "@/components/analytics/ChapterChart";
import type { ChapterChartDatum } from "@/components/analytics/ChapterChart";
import { EventTimeline } from "@/components/analytics/EventTimeline";
import type {
  TimelineEvent,
  TimelineEventType,
} from "@/components/analytics/EventTimeline";
import { useStory, useStoryAnalytics, type StoryAnalytics } from "@/lib/api/queries";
import { rehydrateLibrary, useLibraryStore } from "@/stores/library-store";

const WORDS_PER_MINUTE = 220; // VN reader baseline used by legacy `web/js/reader.ts`.

// Code-split — only loaded when ?show=characters per spec.
const CharacterGraph = dynamic(
  () => import("@/components/branching/CharacterGraph"),
  { ssr: false, loading: () => <p className="text-sm text-muted-foreground">Đang tải đồ thị nhân vật…</p> }
);

interface CharacterShape {
  id?: string;
  name?: string;
  role?: string;
}

function inferEventType(label: string): TimelineEventType {
  const l = label.toLowerCase();
  if (l.includes("rewrite")) return "rewrite";
  if (l.includes("gate") || l.includes("contract")) return "gate";
  if (l.includes("enhance") || l.includes("layer 2") || l.includes("l2")) return "enhancement";
  return "simulation";
}

function countWords(text: string): number {
  const words = text.trim().split(/\s+/).filter(Boolean);
  return words.length;
}

export default function AnalyticsPage() {
  const params = useParams<{ id: string }>();
  const storyId = params?.id ?? null;

  const stories = useLibraryStore((s) => s.stories);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const localStory = React.useMemo(
    () => (storyId ? stories.find((s) => s.id === storyId) ?? null : null),
    [stories, storyId],
  );
  const backendStoryId = storyId && hydrated && !localStory ? storyId : null;

  const analytics = useStoryAnalytics(backendStoryId);
  // We also pull the raw story to source characters for the optional graph
  // when this route points at a backend checkpoint filename instead of a
  // client-side library story id.
  const story = useStory(backendStoryId);

  const [show, setShow] = useQueryState("show");

  React.useEffect(() => {
    rehydrateLibrary();
  }, []);

  // Stable per-mount epoch so re-renders don't shift fallback timestamps.
  // Lazy initializer runs once — keeps the render pure (no Date.now() at render).
  const [epoch] = React.useState(() => Date.now());

  if (!storyId) {
    return <p className="text-sm text-muted-foreground">Không tìm thấy truyện.</p>;
  }
  if (!hydrated) {
    return <p className="text-sm text-muted-foreground">Đang tải thư viện…</p>;
  }

  const localAnalytics: StoryAnalytics | null = localStory
    ? (() => {
        const chapters = localStory.chapters.map((c, i) => ({
          number: i + 1,
          title: c.title || `Chương ${i + 1}`,
          wordCount: countWords(c.content),
        }));
        const wordCount = chapters.reduce((sum, c) => sum + c.wordCount, 0);
        return {
          wordCount,
          chapterCount: chapters.length,
          averageWords: chapters.length > 0 ? Math.round(wordCount / chapters.length) : 0,
          qualityScore: null,
          chapters,
          events: [
            { label: "Tạo truyện", at: localStory.createdAt },
            ...(localStory.updatedAt !== localStory.createdAt
              ? [{ label: "Cập nhật truyện", at: localStory.updatedAt }]
              : []),
          ],
        };
      })()
    : null;

  if (!localAnalytics && analytics.isLoading) {
    return <p className="text-sm text-muted-foreground">Đang tính số liệu…</p>;
  }
  if (!localAnalytics && analytics.error) {
    return (
      <p className="text-sm text-destructive">
        Lỗi tải số liệu: {analytics.error.message}
      </p>
    );
  }
  const a = localAnalytics ?? analytics.data;
  if (!a) {
    return <p className="text-sm text-muted-foreground">Chưa có số liệu.</p>;
  }

  const readingTimeMinutes = a.wordCount > 0 ? a.wordCount / WORDS_PER_MINUTE : 0;

  const chartData: ChapterChartDatum[] = a.chapters.map((c) => ({
    chapter: c.number,
    words: c.wordCount,
  }));

  const timelineEvents: TimelineEvent[] = a.events.map((e, idx) => {
    const parsed = e.at ? Date.parse(e.at) : NaN;
    const ts = Number.isFinite(parsed) ? parsed : epoch - idx * 60_000;
    return {
      ts,
      type: inferEventType(e.label),
      label: e.label,
    };
  });

  const characters: Array<{ id: string; name: string; role?: string }> =
    localStory
      ? localStory.characters.map((c, i) => ({
          id: c.name || String(i),
          name: c.name || `Nhân vật ${i + 1}`,
          role: c.role,
        }))
      : Array.isArray(story.data?.characters)
        ? (story.data!.characters as CharacterShape[]).map((c, i) => ({
            id: c?.id ?? String(i),
            name: c?.name ?? `Nhân vật ${i + 1}`,
            role: c?.role,
          }))
        : [];

  const showCharacters = show === "characters";

  return (
    <div className="flex flex-col gap-4">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Số liệu</h1>
          <p className="text-sm text-muted-foreground">{storyId}</p>
        </div>
        <Button
          type="button"
          variant={showCharacters ? "default" : "outline"}
          size="sm"
          onClick={() => void setShow(showCharacters ? null : "characters")}
          disabled={characters.length === 0}
        >
          {showCharacters ? "Ẩn đồ thị nhân vật" : "Đồ thị nhân vật"}
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <WordCountCard
          total={a.wordCount}
          perChapter={a.averageWords}
          readingTimeMinutes={readingTimeMinutes}
        />
        <QualityCard score={a.qualityScore ?? 0} />
        <Card>
          <CardHeader>
            <CardTitle>Sự kiện</CardTitle>
          </CardHeader>
          <CardContent className="max-h-[320px] overflow-auto pb-4">
            <EventTimeline events={timelineEvents} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Số từ theo chương</CardTitle>
        </CardHeader>
        <CardContent>
          {chartData.length === 0 ? (
            <p className="text-sm text-muted-foreground">Chưa có chương.</p>
          ) : (
            <ChapterChart data={chartData} />
          )}
        </CardContent>
      </Card>

      {showCharacters ? (
        <Card>
          <CardHeader>
            <CardTitle>Quan hệ nhân vật</CardTitle>
          </CardHeader>
          <CardContent className="pb-4">
            {characters.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                Không có dữ liệu nhân vật.
              </p>
            ) : (
              <CharacterGraph characters={characters} />
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
