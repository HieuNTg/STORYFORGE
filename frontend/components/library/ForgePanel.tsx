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

const STAGE_LABEL: Record<ForgeStreamStage, string> = {
  planning: "Đang phác thảo bối cảnh…",
  characters: "Đang tạo nhân vật…",
  chapter: "Đang viết chương 1…",
  choices: "Đang cân nhắc các ngả rẽ…",
};

export function ForgePanel({ onForged, disabled, className }: ForgePanelProps) {
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
    setLog((l) => [...l, `[${new Date().toLocaleTimeString("vi-VN")}] ${line}`]);
  }, []);

  async function handleForge() {
    if (!canForge) return;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setStreaming(true);
    setLog([]);
    appendLog(`Gửi ý tưởng (${len} ký tự)…`);
    try {
      const story = await forgeFromSentenceStream(
        { sentenceIdea: sentence.trim() },
        {
          signal: ctrl.signal,
          onStage: (stage) => appendLog(STAGE_LABEL[stage]),
          onError: (err) => appendLog(`Lỗi: ${err.message}`),
        },
      );
      appendLog(`Hoàn thành: "${story.title}"`);
      onForged(story);
      setSentence("");
      toast.success("Đã tạo truyện mới", { description: story.title });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      if (!ctrl.signal.aborted) {
        toast.error("Forge thất bại", { description: msg });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function handleCancel() {
    abortRef.current?.abort();
    appendLog("Đã huỷ.");
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
          Forge từ một câu ý tưởng
        </h2>
      </header>

      <Textarea
        value={sentence}
        onChange={(e) => setSentence(e.target.value)}
        placeholder="VD: Một kiếm khách bị phế võ công đi tìm sư phụ đã chết để hỏi tội…"
        maxLength={MAX_LEN + 50}
        rows={3}
        disabled={streaming || disabled}
        aria-invalid={tooShort || tooLong || undefined}
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
            ? `Cần ít nhất ${MIN_LEN} ký tự`
            : tooLong
              ? `Vượt ${MAX_LEN} ký tự`
              : `Tối đa ${MAX_LEN} ký tự`}
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
          {streaming ? "Đang forge…" : "Forge truyện"}
        </Button>
        {streaming && (
          <Button type="button" variant="outline" onClick={handleCancel}>
            Huỷ
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
