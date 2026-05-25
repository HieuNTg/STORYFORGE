"use client";

/**
 * ForgePanel — 1-Click Forge-from-Sentence UI.
 *
 * Sentence textarea (max 500) → Sparkles button → SSE stream from
 * `/api/forge/sentence/stream`. Live mono log autoscrolls; Forge button
 * disabled while streaming. On `forge.final`, calls `onForged(story)` so the
 * host can persist into the library store.
 */

import * as React from "react";
import { motion, useReducedMotion } from "motion/react";
import { Sparkles, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  forgeFromSentenceStream,
  type ForgeStreamStage,
} from "@/lib/api/forge";
import type { ForgeResponse } from "@/types/story";

export interface ForgePanelProps {
  onForged: (response: ForgeResponse) => void;
  disabled?: boolean;
  className?: string;
}

const MAX_LEN = 500;
const MIN_LEN = 10;

const STAGE_KEYS: Record<ForgeStreamStage, string> = {
  planning: "forge_stage_planning",
  characters: "forge_stage_characters",
  chapter: "forge_stage_chapter",
  choices: "forge_stage_choices",
};

export function ForgePanel({ onForged, disabled, className }: ForgePanelProps) {
  const t = useTranslations("library");
  const reduce = useReducedMotion();
  const [sentence, setSentence] = React.useState("");
  const [streaming, setStreaming] = React.useState(false);
  const [log, setLog] = React.useState<string[]>([]);
  const abortRef = React.useRef<AbortController | null>(null);
  const logRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [log]);

  React.useEffect(() => () => abortRef.current?.abort(), []);

  const len = sentence.trim().length;
  const tooShort = len > 0 && len < MIN_LEN;
  const tooLong = len > MAX_LEN;
  const canForge = !disabled && !streaming && len >= MIN_LEN && !tooLong;

  const appendLog = React.useCallback((line: string) => {
    setLog((l) => [...l, `[${new Date().toLocaleTimeString()}] ${line}`]);
  }, []);

  async function handleForge() {
    if (!canForge) return;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    setLog([]);
    appendLog(t("forge_sending", { count: len }));
    try {
      const story = await forgeFromSentenceStream(
        { sentenceIdea: sentence.trim() },
        {
          signal: ctrl.signal,
          onStage: (stage) => appendLog(t(STAGE_KEYS[stage])),
          onError: (err) => appendLog(t("error_with_message", { msg: err.message })),
        },
      );
      appendLog(t("forge_done", { title: story.title }));
      onForged(story);
      setSentence("");
      toast.success(t("created_new"), { description: story.title });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!ctrl.signal.aborted) {
        toast.error(t("forge_failed"), { description: msg });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    appendLog(t("cancelled"));
    setStreaming(false);
  }

  return (
    <section
      className={cn(
        "rounded-xl border border-border/60 bg-card/70 p-4 shadow-sm backdrop-blur",
        className,
      )}
      aria-labelledby="forge-panel-title"
    >
      <header className="mb-3 flex items-center gap-2">
        <Sparkles className="size-4 text-[var(--color-accent,#C5A47E)]" aria-hidden />
        <h2 id="forge-panel-title" className="text-sm font-semibold">
          {t("forge_title")}
        </h2>
      </header>

      <Textarea
        value={sentence}
        onChange={(e) => setSentence(e.target.value)}
        placeholder={t("forge_placeholder")}
        maxLength={MAX_LEN + 50}
        rows={3}
        disabled={streaming || disabled}
        aria-invalid={tooShort || tooLong || undefined}
        aria-labelledby="forge-panel-title"
        aria-describedby="forge-help"
        className="resize-none"
      />

      <div id="forge-help" className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
        <span
          className={cn(
            tooShort && "text-amber-500",
            tooLong && "text-destructive",
          )}
        >
          {tooShort
            ? t("min_chars", { min: MIN_LEN })
            : tooLong
              ? t("over_chars", { max: MAX_LEN })
              : t("max_chars", { max: MAX_LEN })}
        </span>
        <span className="tabular-nums">
          {len} / {MAX_LEN}
        </span>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <Button
          type="button"
          onClick={handleForge}
          disabled={!canForge}
          className="gap-1.5"
        >
          {streaming ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <Sparkles className="size-4" aria-hidden />
          )}
          {streaming ? t("forging") : t("forge_cta")}
        </Button>
        {streaming && (
          <Button type="button" variant="outline" onClick={handleCancel}>
            {t("cancel")}
          </Button>
        )}
      </div>

      {log.length > 0 && (
        <motion.div
          initial={reduce ? false : { opacity: 0, height: 0 }}
          animate={reduce ? undefined : { opacity: 1, height: "auto" }}
          transition={reduce ? undefined : { duration: 0.2 }}
          className="mt-3"
        >
          <div
            ref={logRef}
            role="log"
            aria-live="polite"
            aria-atomic="false"
            className="max-h-40 overflow-y-auto rounded-md border border-border/60 bg-muted/40 p-2 font-mono text-xs leading-relaxed text-muted-foreground"
          >
            {log.map((line, i) => (
              <div key={i}>{line}</div>
            ))}
          </div>
        </motion.div>
      )}
    </section>
  );
}

