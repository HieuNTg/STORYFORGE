"use client";

/**
 * Khai sinh — the canonical entry point for spec-to-story generation.
 *
 * Hosts the full `/api/pipeline/run` flow (via `PipelineScreen`) wrapped with:
 *   - An L1 / L2 mode toggle (single source of truth for the run's depth).
 *   - A "Lưu vào thư viện" CTA on the result panel that maps the pipeline's
 *     `done.data` summary onto a `Story` and pushes it into `useLibraryStore`.
 *
 * Locked product decisions (do not re-litigate inside the page):
 *   - This page uses the full pipeline. The cheap 1-sentence forge stays
 *     inside the Library and is unaffected.
 *   - L1 and L2 live behind a single toggle here; backend pipelines remain
 *     independent (CLAUDE.md). The toggle just composes the request payload.
 *   - Sidebar PRIMARY count stays locked at 7 — no new nav entry.
 */

import * as React from "react";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { BookmarkPlus, BookmarkCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PipelineScreen } from "@/components/pipeline/PipelineScreen";
import type { PipelineMode } from "@/components/pipeline/PipelineForm";
import {
  useLibraryStore,
  rehydrateLibrary,
  LIBRARY_MAX_STORIES,
} from "@/stores/library-store";
import {
  pipelineSummaryToStory,
  type PipelineDoneSummary,
} from "@/lib/library/story-mappers";
import { cn } from "@/lib/utils";

/**
 * Visual L1 / L2 segmented control. Lives inside the form card via
 * `PipelineScreen`'s `formHeader` slot so the toggle moves with the form
 * column at narrow widths.
 */
function ModeToggle({
  mode,
  onChange,
  disabled,
  l1Label,
  l2Label,
  l1Description,
  l2Description,
  ariaLabel,
}: {
  mode: PipelineMode;
  onChange: (m: PipelineMode) => void;
  disabled?: boolean;
  l1Label: string;
  l2Label: string;
  l1Description: string;
  l2Description: string;
  ariaLabel: string;
}) {
  const items: Array<{ key: PipelineMode; label: string; desc: string }> = [
    { key: "l1", label: l1Label, desc: l1Description },
    { key: "l2", label: l2Label, desc: l2Description },
  ];
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="grid grid-cols-2 gap-2"
    >
      {items.map((item) => {
        const active = mode === item.key;
        return (
          <button
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled}
            key={item.key}
            onClick={() => onChange(item.key)}
            className={cn(
              "flex flex-col items-start gap-0.5 rounded-md border px-3 py-2 text-left text-sm transition-colors",
              "disabled:cursor-not-allowed disabled:opacity-50",
              active
                ? "border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_8%,transparent)] text-[var(--accent-strong)]"
                : "border-border bg-card text-foreground hover:bg-[color-mix(in_oklab,var(--accent)_5%,transparent)]"
            )}
          >
            <span className="font-medium">{item.label}</span>
            <span className="text-[11px] leading-tight text-muted-foreground">
              {item.desc}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export default function ForgePage() {
  const t = useTranslations("forge");
  const tNav = useTranslations("nav_desc");
  const [mode, setMode] = React.useState<PipelineMode>("l2");
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
        mode={mode}
        formHeader={
          <ModeToggle
            mode={mode}
            onChange={setMode}
            ariaLabel={t("mode_label")}
            l1Label={t("mode_l1")}
            l2Label={t("mode_l2")}
            l1Description={t("mode_l1_desc")}
            l2Description={t("mode_l2_desc")}
          />
        }
        onResult={handleResult}
        resultAction={saveButton}
      />
    </div>
  );
}
