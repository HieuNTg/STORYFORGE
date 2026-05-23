"use client";

/**
 * Khai sinh — the canonical entry point for spec-to-story generation.
 *
 * Hosts the full `/api/pipeline/run` flow (via `PipelineScreen`) plus a
 * "Lưu vào thư viện" CTA on the result panel that maps the pipeline's
 * `done.data` summary onto a `Story` and pushes it into `useLibraryStore`.
 *
 * Locked product decisions (do not re-litigate inside the page):
 *   - Every run uses the full A-Z pipeline (L1 → L2). No user-facing mode
 *     picker — CEO decision.
 *   - The cheap 1-sentence forge stays inside the Library and is unaffected.
 *   - Sidebar PRIMARY count stays locked at 7 — no new nav entry.
 */

import * as React from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { BookmarkPlus, BookmarkCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PipelineScreen } from "@/components/pipeline/PipelineScreen";
import {
  useLibraryStore,
  rehydrateLibrary,
  LIBRARY_MAX_STORIES,
} from "@/stores/library-store";
import {
  pipelineSummaryToStory,
  type PipelineDoneSummary,
} from "@/lib/library/story-mappers";

export default function ForgePage() {
  const t = useTranslations("forge");
  const tNav = useTranslations("nav_desc");
  const [doneSummary, setDoneSummary] =
    React.useState<PipelineDoneSummary | null>(null);
  const [savedStoryId, setSavedStoryId] = React.useState<string | null>(null);

  const addStory = useLibraryStore((s) => s.addStory);
  const selectStory = useLibraryStore((s) => s.selectStory);

  // Ensure the persisted library is hydrated before the user clicks Save —
  // otherwise the cap check would race against the localStorage load.
  React.useEffect(() => {
    rehydrateLibrary();
  }, []);

  // Resetting saved state when a new run begins is implicit: a new `done`
  // event clobbers `doneSummary` with a fresh id, so the button re-enables.
  const handleResult = React.useCallback((raw: unknown) => {
    if (!raw || typeof raw !== "object") return;
    // Backend emits `{type:'done', data: <summary>}`; pipelineBridge unwraps
    // the envelope once but some callers still receive a nested `data` field.
    const maybeWrapped = raw as { data?: unknown } & Record<string, unknown>;
    const inner =
      maybeWrapped && typeof maybeWrapped === "object" && maybeWrapped.data &&
      typeof maybeWrapped.data === "object"
        ? (maybeWrapped.data as PipelineDoneSummary)
        : (raw as PipelineDoneSummary);
    setDoneSummary(inner);
    setSavedStoryId(null);
  }, []);

  const handleSave = React.useCallback(() => {
    const story = pipelineSummaryToStory(doneSummary);
    if (!story) {
      toast.error(t("save_failed_empty"));
      return;
    }
    const ok = addStory(story);
    if (!ok) {
      toast.error(t("save_failed_full", { max: LIBRARY_MAX_STORIES }));
      return;
    }
    setSavedStoryId(story.id);
    selectStory(story.id);
    toast.success(t("save_success"), { description: story.title });
  }, [doneSummary, addStory, selectStory, t]);

  const saveButton = (
    <Button
      type="button"
      variant={savedStoryId ? "outline" : "default"}
      onClick={handleSave}
      disabled={!doneSummary || !!savedStoryId}
      aria-label={savedStoryId ? t("save_saved") : t("save")}
    >
      {savedStoryId ? (
        <>
          <BookmarkCheck aria-hidden />
          {t("save_saved")}
        </>
      ) : (
        <>
          <BookmarkPlus aria-hidden />
          {t("save")}
        </>
      )}
    </Button>
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{tNav("forge")}</p>
      </header>

      <PipelineScreen
        onResult={handleResult}
        resultAction={saveButton}
      />
    </div>
  );
}
