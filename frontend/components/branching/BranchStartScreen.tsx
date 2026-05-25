"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { BookOpen, GitBranch, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api/client";
import {
  rehydrateLibrary,
  useLibraryStore,
} from "@/stores/library-store";
import type { Story } from "@/types/story";
import { displayStoryTitle } from "@/lib/library/display-helpers";

interface StartBranchResponse {
  session_id: string;
}

function FieldLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">
      {children}
    </label>
  );
}

function storyText(story: Story, chapterId: string, tSelectChapter: string): string {
  if (chapterId === "__all__") {
    const chapters = story.chapters
      .map((chapter, idx) => {
        const title = chapter.title || `${tSelectChapter} ${idx + 1}`;
        return [`# ${title}`, chapter.summary, chapter.content].filter(Boolean).join("\n\n");
      })
      .filter(Boolean);
    return chapters.join("\n\n---\n\n") || story.description;
  }
  const chapter = story.chapters.find((c) => c.id === chapterId);
  if (!chapter) return story.description;
  return [chapter.title, chapter.summary, chapter.content].filter(Boolean).join("\n\n");
}

export function BranchStartScreen() {
  const router = useRouter();
  const t = useTranslations("branching");
  const tLib = useTranslations("library");
  const stories = useLibraryStore((s) => s.stories);
  const selectedId = useLibraryStore((s) => s.selectedId);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const [storyId, setStoryId] = React.useState<string>("");
  const [chapterId, setChapterId] = React.useState<string>("__all__");
  const [conflictSummary, setConflictSummary] = React.useState("");
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    rehydrateLibrary();
  }, []);

  React.useEffect(() => {
    if (!storyId && selectedId && stories.some((s) => s.id === selectedId)) {
      setStoryId(selectedId);
      return;
    }
    if (!storyId && stories.length > 0) setStoryId(stories[0].id);
  }, [selectedId, stories, storyId]);

  const selectedStory = React.useMemo(
    () => stories.find((s) => s.id === storyId) ?? null,
    [stories, storyId],
  );

  React.useEffect(() => {
    setChapterId("__all__");
    setConflictSummary(selectedStory?.description ?? "");
  }, [selectedStory?.id, selectedStory?.description]);

  const branchText = selectedStory ? storyText(selectedStory, chapterId, t("range_chapter_label")).trim() : "";
  const canSubmit = !!selectedStory && branchText.length >= 10 && !loading;

  async function startSession() {
    if (!selectedStory || !canSubmit) return;
    setLoading(true);
    try {
      const res = await apiFetch<StartBranchResponse>("/api/branch/start", {
        method: "POST",
        body: JSON.stringify({
          text: branchText,
          genre: selectedStory.genre,
          // Forward source story language so branching continuations and
          // choice labels are generated in the story's language.
          language: selectedStory.language || "vi",
          world_summary: selectedStory.setting,
          conflict_summary: conflictSummary.trim() || selectedStory.description,
          characters: selectedStory.characters.map((c) => ({
            name: c.name,
            role: c.role,
            personality: c.description || c.backstory || "",
          })),
        }),
      });
      toast.success(t("session_created"), { description: selectedStory.title });
      router.push(`/branching/${encodeURIComponent(res.session_id)}/`);
    } catch (err) {
      const message = err instanceof Error ? err.message : t("session_create_failed");
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }

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
            <p className="mt-1 text-sm text-muted-foreground">
              {t("empty_hint")}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <section>
      <div className="rounded-lg border border-border/70 bg-card p-5 shadow-sm">
        <div className="mb-5 flex items-start gap-3">
          <span className="rounded-md border border-[var(--accent)]/30 bg-[color-mix(in_oklab,var(--accent)_10%,transparent)] p-2 text-[var(--accent-strong)]">
            <GitBranch className="size-5" aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-lg font-medium text-foreground">{t("select_title")}</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("select_hint")}
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <FieldLabel htmlFor="branch-story">{t("select_story")}</FieldLabel>
              <select
                id="branch-story"
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
            </div>

            <div className="space-y-2">
              <FieldLabel htmlFor="branch-chapter">{t("range_label")}</FieldLabel>
              <select
                id="branch-chapter"
                value={chapterId}
                onChange={(e) => setChapterId(e.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <option value="__all__">{t("range_all")}</option>
                {selectedStory?.chapters.map((chapter, idx) => (
                  <option key={chapter.id} value={chapter.id}>
                    {chapter.title || t("range_chapter", { num: idx + 1 })}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <FieldLabel htmlFor="branch-setting">{t("setting_label")}</FieldLabel>
              <Input id="branch-setting" value={selectedStory?.setting ?? ""} readOnly />
            </div>
            <div className="space-y-2">
              <FieldLabel htmlFor="branch-conflict">{t("conflict_label")}</FieldLabel>
              <Input
                id="branch-conflict"
                value={conflictSummary}
                onChange={(e) => setConflictSummary(e.target.value)}
                placeholder={t("conflict_placeholder")}
              />
            </div>
          </div>

          <div className="rounded-md border border-border/70 bg-muted/30 p-3 text-sm text-muted-foreground">
            <div className="font-medium text-foreground">{selectedStory?.title}</div>
            <div className="mt-1 line-clamp-2">{selectedStory?.description || t("no_description")}</div>
            <div className="mt-2 text-xs">
              {t("source_info", { chars: branchText.length.toLocaleString(), characters: selectedStory?.characters.length ?? 0 })}
            </div>
          </div>

          <Button type="button" onClick={startSession} disabled={!canSubmit}>
            {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <GitBranch className="mr-2 size-4" />}
            {t("start_cta")}
          </Button>
        </div>
      </div>
    </section>
  );
}
