"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, BookOpen, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { rehydrateLibrary, useLibraryStore } from "@/stores/library-store";
import { forgeFromSentenceStream } from "@/lib/api/forge";
import type { StoryChapter } from "@/types/story";
import { displayStoryTitle } from "@/lib/library/display-helpers";

const STAGE_LABEL: Record<string, string> = {
  planning: "Đang lập kế hoạch",
  characters: "Đang giữ mạch nhân vật",
  chapter: "Đang viết chương",
  choices: "Đang hoàn thiện",
};

export function ContinueStoryScreen() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryId = searchParams?.get("id") ?? null;

  const stories = useLibraryStore((s) => s.stories);
  const selectedId = useLibraryStore((s) => s.selectedId);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const selectStory = useLibraryStore((s) => s.selectStory);
  const appendChapter = useLibraryStore((s) => s.appendChapter);

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

  const buildIdea = React.useCallback(
    (chapterNumber: number) => {
      if (!story) return "";
      const lastChapter = story.chapters.at(-1);
      const characters = story.characters.map((c) => c.name).filter(Boolean).slice(0, 8).join(", ");
      const automaticDirection =
        "Không có chỉ đạo riêng: hãy tự nối tiếp từ chương cuối, giữ đúng thể loại, tông giọng, nhân vật và mở thêm cao trào hợp lý.";
      return [
        `Viết tiếp truyện "${story.title}".` ,
        story.genre ? `Thể loại: ${story.genre}.` : "",
        story.tone ? `Tông giọng: ${story.tone}.` : "",
        story.description ? `Tóm tắt truyện: ${story.description}` : "",
        characters ? `Nhân vật chính/phụ đã biết: ${characters}.` : "",
        lastChapter
          ? `Chương gần nhất: ${lastChapter.title}. ${lastChapter.summary || lastChapter.content.slice(0, 220)}`
          : "Truyện chưa có chương; hãy viết chương mở đầu phù hợp với tiền đề.",
        `Đây là chương viết tiếp số ${chapterNumber}.`,
        direction.trim() ? `Chỉ đạo của người dùng: ${direction.trim()}` : automaticDirection,
      ]
        .filter(Boolean)
        .join(" ")
        .slice(0, 500);
    },
    [direction, story],
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
          createdAt: now,
        };
        appendChapter(story.id, chapter);
        setWritten(i + 1);
      }
      toast.success("Đã viết tiếp truyện", {
        description: `${chapterCount} chương mới đã được thêm vào thư viện.`,
      });
      router.push(`/reader/?id=${encodeURIComponent(story.id)}`);
    } catch (err) {
      toast.error("Viết tiếp thất bại", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsWriting(false);
      setStage(null);
    }
  }, [appendChapter, buildIdea, chapterCount, isWriting, router, story]);

  if (!hydrated) {
    return <div className="rounded-xl border border-border/60 bg-card p-5 text-sm text-muted-foreground">Đang tải thư viện…</div>;
  }

  if (stories.length === 0) {
    return <div className="rounded-xl border border-border/60 bg-card p-5 text-sm text-muted-foreground">Chưa có truyện để viết tiếp. Hãy tạo hoặc nhập truyện trong Thư viện trước.</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-medium text-foreground">Viết tiếp truyện</h1>
          <p className="text-sm text-muted-foreground">Thiết kế mạch tiếp theo, chọn số chương, rồi sinh chương mới vào thư viện.</p>
        </div>
        <Button type="button" variant="outline" onClick={() => router.push("/library/")}> 
          <ArrowLeft className="size-4" aria-hidden />
          Về Thư viện
        </Button>
      </div>

      <section className="rounded-xl border border-border/60 bg-card/70 p-5 shadow-sm">
        <div className="grid gap-4 md:grid-cols-[1fr_180px]">
          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>Truyện</span>
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
                <option key={s.id} value={s.id}>{displayStoryTitle(s, "Truyện chưa đặt tên")} · {s.chapters.length} chương</option>
              ))}
            </select>
          </label>

          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>Số chương viết tiếp</span>
            <input
              type="number"
              min={1}
              max={10}
              value={chapterCount}
              onChange={(e) => setChapterCount(Math.max(1, Math.min(10, Number(e.target.value) || 1)))}
              disabled={isWriting}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
        </div>

        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_280px]">
          <label className="space-y-2 text-sm font-medium text-foreground">
            <span>Hướng viết tiếp (tuỳ chọn)</span>
            <Textarea
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              maxLength={500}
              disabled={isWriting}
              className="min-h-36"
              placeholder="VD: Cho nhân vật chính gặp phản diện trong bí cảnh, hé lộ bí mật nhưng chưa giải quyết hết. Để trống nếu muốn AI tự nối mạch từ chương cuối."
            />
            <span className="block text-xs text-muted-foreground">{direction.length} / 500 · Để trống = AI tự viết tiếp theo mạch truyện hiện có.</span>
          </label>

          <div className="rounded-lg border border-border/60 bg-background/45 p-4 text-sm">
            <div className="mb-3 flex items-center gap-2 font-medium text-foreground">
              <BookOpen className="size-4" aria-hidden />
              Ngữ cảnh sẽ dùng
            </div>
            <ul className="space-y-2 text-muted-foreground">
              <li>• Tên, thể loại, tông giọng truyện</li>
              <li>• Mô tả/tóm tắt hiện có</li>
              <li>• Chương cuối cùng</li>
              <li>• Danh sách nhân vật nếu có</li>
              <li>• Hướng phát triển tuỳ chọn</li>
            </ul>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">
            {isWriting
              ? `${STAGE_LABEL[stage ?? ""] ?? "Đang viết"} · ${written}/${chapterCount} chương xong`
              : "Hoàn tất sẽ chuyển sang Đọc truyện."}
          </p>
          <Button type="button" onClick={() => void handleWrite()} disabled={!story || isWriting}>
            <Sparkles className="size-4" aria-hidden />
            {isWriting ? "Đang viết…" : `Viết tiếp ${chapterCount} chương`}
          </Button>
        </div>
      </section>
    </div>
  );
}
