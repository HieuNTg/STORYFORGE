"use client";

/**
 * PipelineScreen — client wrapper that wires the form, SSE bridge, and the
 * Designer's visual components together.
 *
 * Responsibilities:
 *   - Hold the request payload that triggers `usePostStream`.
 *   - Apply each SSE frame via `applySseEventToStores`.
 *   - Bind store snapshots to TheaterPanel + ResultPanel props.
 *   - Persist the active `session_id` to nuqs `?session=` for resume on reload.
 */

import * as React from "react";
import { useQueryState } from "nuqs";
import { toast } from "sonner";
import { useShallow } from "zustand/react/shallow";
import {
  loadStartedAt,
  saveStartedAt,
  clearStartedAt,
} from "@/lib/sse/startedAtStore";
import { Card, CardContent } from "@/components/ui/card";
import { PipelineForm } from "./PipelineForm";
import { TheaterPanel } from "./TheaterPanel";
import { ResultPanel, type ResultStory } from "./ResultPanel";
import { usePostStream } from "@/lib/sse/usePostStream";
import { applySseEventToStores } from "@/lib/sse/pipelineBridge";
import { usePipelineStore } from "@/stores/pipeline-store";
import { useTheaterStore } from "@/stores/theater-store";
import type { CreateStoryRequest } from "@/lib/api/queries";
import type { AgentBubbleProps } from "./AgentBubble";

export interface PipelineScreenProps {
  /**
   * Optional header rendered above the form column.
   */
  formHeader?: React.ReactNode;
  /**
   * Fires when a run finishes. Receives the raw `done.data` summary from
   * `/api/pipeline/run`, suitable for `pipelineSummaryToStory`. Enables
   * the Khai sinh "Save to library" CTA without re-parsing internal state.
   */
  onResult?: (rawDone: unknown) => void;
  /**
   * Optional action node rendered in the `ResultPanel` header (e.g. a
   * "Save to library" button). Hidden until a run has completed.
   */
  resultAction?: React.ReactNode;
  /**
   * Fires when the form passes validation and the run is about to start.
   * Receives the full `CreateStoryRequest` so callers can capture the
   * requested `num_chapters` (= target total length) for later persistence.
   */
  onSubmit?: (req: CreateStoryRequest) => void;
}

export function PipelineScreen({
  formHeader,
  onResult,
  resultAction,
  onSubmit: externalOnSubmit,
}: PipelineScreenProps = {}) {
  const [sessionQuery, setSessionQuery] = useQueryState("session");
  const [pendingBody, setPendingBody] = React.useState<CreateStoryRequest | null>(
    null
  );
  const [resultStory, setResultStory] = React.useState<ResultStory | undefined>();
  const [startedAt, setStartedAt] = React.useState<number | null>(null);
  const [requestedChapters, setRequestedChapters] = React.useState<number | null>(
    null
  );

  const phases = usePipelineStore((s) => s.phases);
  const currentPhase = usePipelineStore((s) => s.currentPhase);
  const status = usePipelineStore((s) => s.status);
  const sessionId = usePipelineStore((s) => s.sessionId);

  const { agents, quality, characters, debateMarker, partialChapters, phaseStats } =
    useTheaterStore(
      useShallow((s) => ({
        agents: s.agents,
        quality: s.quality,
        characters: s.characters,
        debateMarker: s.debateMarker,
        partialChapters: s.partialChapters,
        phaseStats: s.phaseStats,
      })),
    );

  // Keep nuqs `?session=` in sync with the store's session id.
  React.useEffect(() => {
    if (sessionId && sessionId !== sessionQuery) {
      void setSessionQuery(sessionId);
    }
  }, [sessionId, sessionQuery, setSessionQuery]);

  // ── startedAt persistence (resume the timer across reloads) ───────────────
  // Lifecycle:
  //   1. Fresh submit → onSubmit sets startedAt = Date.now(). The effect below
  //      then persists it once the SSE session id is known.
  //   2. Reload mid-run → sessionQuery is still in the URL, sessionId hydrates
  //      from it via the bridge, and the mount effect rehydrates startedAt
  //      from sessionStorage so the timer keeps counting from the original
  //      start instant rather than from 0.
  //   3. done/error/interrupted → clear the persisted entry so the next run
  //      doesn't accidentally inherit a stale baseline.

  // Hydrate on mount: if a session is already in the URL but we don't have a
  // startedAt in component state, try sessionStorage. Uses ref to ensure this
  // only runs once per mount (avoids racing with the save effect below).
  const hydratedRef = React.useRef(false);
  React.useEffect(() => {
    if (hydratedRef.current) return;
    if (startedAt != null) {
      hydratedRef.current = true;
      return;
    }
    const sid = sessionId ?? sessionQuery;
    if (!sid) return;
    const persisted = loadStartedAt(sid);
    if (persisted != null) {
      setStartedAt(persisted);
    }
    hydratedRef.current = true;
  }, [sessionId, sessionQuery, startedAt]);

  // Persist startedAt once we know the session id (sessionId is set by the
  // bridge from the SSE `session` frame, which arrives shortly after submit).
  React.useEffect(() => {
    if (sessionId && startedAt != null) {
      saveStartedAt(sessionId, startedAt);
    }
  }, [sessionId, startedAt]);

  // Clear persistence + local timer when the run reaches a terminal state.
  React.useEffect(() => {
    if (status === "done" || status === "error" || status === "interrupted") {
      clearStartedAt(sessionId);
      // Keep `startedAt` non-null so the TheaterPanel can show the final
      // elapsed time; the persisted entry is what we must drop so a future
      // fresh run on the same tab doesn't inherit a stale baseline.
    }
  }, [status, sessionId]);

  const handleMessage = React.useCallback(
    (event: { data: string }) => {
      applySseEventToStores(event, {
        onChapterComplete: (label) => toast.success(`Hoàn tất ${label}`),
        onDone: (payload) => {
          const story = buildResultStoryFromDone(payload);
          if (story) setResultStory(story);
          // Expose the raw `done.data` for richer consumers (e.g. save-to-library).
          // PipelineBridge already unwrapped the outer envelope; some backends
          // double-wrap the payload, so forward whatever we got.
          onResult?.(payload);
          toast.success("Sinh truyện hoàn tất");
        },
        onError: (msg) => toast.error(msg || "Pipeline thất bại"),
        onInterrupted: () => toast.warning("Kết nối bị gián đoạn"),
      });
    },
    [onResult]
  );

  const stream = usePostStream({
    url: pendingBody ? "/api/pipeline/run" : null,
    body: pendingBody as Record<string, unknown> | null,
    onMessage: handleMessage,
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "Stream error";
      toast.error(msg);
    },
  });

  const onSubmit = React.useCallback(
    (req: CreateStoryRequest) => {
      // Reset stores for a fresh run.
      usePipelineStore.getState().start(null);
      useTheaterStore.getState().reset();
      setResultStory(undefined);
      setStartedAt(Date.now());
      const reqChapters =
        typeof (req as { num_chapters?: number }).num_chapters === "number"
          ? (req as { num_chapters?: number }).num_chapters!
          : null;
      setRequestedChapters(reqChapters);
      setPendingBody(req);
      externalOnSubmit?.(req);
    },
    [externalOnSubmit],
  );

  const handleCancel = React.useCallback(() => {
    stream.abort();
    setPendingBody(null);
    usePipelineStore.getState().setStatus("interrupted");
    toast.warning("Đã huỷ phiên sinh truyện");
  }, [stream]);

  const pending = status === "running" || stream.readyState === "connecting";

  // Map theater agents → AgentBubble props, forwarding partial buffer + role.
  const agentBubbleProps: AgentBubbleProps[] = React.useMemo(
    () =>
      agents.map((a) => ({
        name: a.name,
        role: a.role,
        status: a.status,
        message: a.message,
        partial: a.partial,
        turn: a.turn,
      })),
    [agents]
  );

  const qualityPct = Math.round(quality.value * 100);
  const characterList = React.useMemo(
    () => characters.map((c) => ({ id: c.id, name: c.name })),
    [characters]
  );

  // Inject the requested chapter count into phaseStats[1].total so the
  // Layer 1 progress bar renders a meaningful percentage.
  const phaseSubInfo = React.useMemo(() => {
    if (!requestedChapters) return phaseStats;
    const prev1 = phaseStats[1];
    return {
      ...phaseStats,
      1: {
        ...prev1,
        total: prev1?.total ?? requestedChapters,
      },
    };
  }, [phaseStats, requestedChapters]);

  // ETA heuristic: ~22s per chapter for L1, plus a flat 90s envelope for L2
  // post-processing. Refined later from real telemetry.
  const etaSeconds = React.useMemo(() => {
    if (!requestedChapters || requestedChapters <= 0) return undefined;
    return Math.max(60, requestedChapters * 22 + 90);
  }, [requestedChapters]);

  // Convert theater partialChapters → ResultPanel partial-chapter shape.
  const resultPartials = React.useMemo(
    () =>
      partialChapters.map((c) => ({
        id: c.id,
        number: c.number,
        title: c.title,
        appendedAt: c.appendedAt,
      })),
    [partialChapters]
  );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(480px,38%)_1fr]">
      <Card>
        <CardContent className="space-y-4">
          {formHeader}
          <PipelineForm onSubmit={onSubmit} pending={pending} />
        </CardContent>
      </Card>

      <div className="flex flex-col gap-6">
        <TheaterPanel
          phases={phases}
          currentPhase={currentPhase}
          phaseSubInfo={phaseSubInfo}
          agents={agentBubbleProps}
          quality={qualityPct}
          qualityLayer={quality.layer}
          qualityUpdatedAt={quality.updatedAt}
          characters={characterList}
          debateMarker={debateMarker ?? undefined}
          startedAt={startedAt ?? undefined}
          etaSeconds={etaSeconds}
          running={pending}
          onCancel={pending ? handleCancel : undefined}
        />
        <ResultPanel
          story={resultStory}
          partialChapters={!resultStory ? resultPartials : undefined}
          totalChapters={requestedChapters ?? undefined}
          headerAction={resultStory ? resultAction : undefined}
        />
      </div>
    </div>
  );
}

interface DoneInner {
  title?: string;
  session_id?: string;
  draft?: {
    chapters?: Array<{
      number?: number;
      title?: string;
      content?: string;
      word_count?: number;
    }>;
  };
}

interface DoneShape extends DoneInner {
  data?: DoneInner;
}

function buildResultStoryFromDone(payload: unknown): ResultStory | null {
  if (!payload || typeof payload !== "object") return null;
  const p = payload as DoneShape;
  // Backend sometimes wraps result in `{type:'done', data: {...}}`. We've
  // already unwrapped the outer envelope in the bridge; payload here may be
  // the inner result *or* the wrapper. Be defensive.
  const inner: DoneInner = p.data ?? p;
  const chapters = inner.draft?.chapters ?? [];
  if (chapters.length === 0) return null;
  return {
    id: inner.session_id ?? "current",
    title: inner.title ?? "Truyện mới",
    chapters: chapters.map((c, idx) => ({
      id: String(c.number ?? idx + 1),
      title: c.title ?? `Chương ${c.number ?? idx + 1}`,
      word_count:
        typeof c.word_count === "number"
          ? c.word_count
          : (c.content ?? "").length,
    })),
  };
}
