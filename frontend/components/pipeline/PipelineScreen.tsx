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

export function PipelineScreen() {
  const [sessionQuery, setSessionQuery] = useQueryState("session");
  const [pendingBody, setPendingBody] = React.useState<CreateStoryRequest | null>(
    null
  );
  const [resultStory, setResultStory] = React.useState<ResultStory | undefined>();

  const phases = usePipelineStore((s) => s.phases);
  const currentPhase = usePipelineStore((s) => s.currentPhase);
  const status = usePipelineStore((s) => s.status);
  const sessionId = usePipelineStore((s) => s.sessionId);

  const { agents, quality, characters, debateMarker } = useTheaterStore(
    useShallow((s) => ({
      agents: s.agents,
      quality: s.quality,
      characters: s.characters,
      debateMarker: s.debateMarker,
    }))
  );

  // Keep nuqs `?session=` in sync with the store's session id.
  React.useEffect(() => {
    if (sessionId && sessionId !== sessionQuery) {
      void setSessionQuery(sessionId);
    }
  }, [sessionId, sessionQuery, setSessionQuery]);

  const handleMessage = React.useCallback((event: { data: string }) => {
    applySseEventToStores(event, {
      onChapterComplete: (label) => toast.success(`Hoàn tất ${label}`),
      onDone: (payload) => {
        const story = buildResultStoryFromDone(payload);
        if (story) setResultStory(story);
        toast.success("Sinh truyện hoàn tất");
      },
      onError: (msg) => toast.error(msg || "Pipeline thất bại"),
      onInterrupted: () => toast.warning("Kết nối bị gián đoạn"),
    });
  }, []);

  const stream = usePostStream({
    url: pendingBody ? "/api/pipeline/run" : null,
    body: pendingBody as Record<string, unknown> | null,
    onMessage: handleMessage,
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "Stream error";
      toast.error(msg);
    },
  });

  const onSubmit = React.useCallback((req: CreateStoryRequest) => {
    // Reset stores for a fresh run.
    usePipelineStore.getState().start(null);
    useTheaterStore.getState().reset();
    setResultStory(undefined);
    setPendingBody(req);
  }, []);

  const pending = status === "running" || stream.readyState === "connecting";

  // Map theater agents → AgentBubble props.
  const agentBubbleProps: AgentBubbleProps[] = React.useMemo(
    () =>
      agents.map((a) => ({
        name: a.name,
        status: a.status,
        message: a.message,
        turn: a.turn,
      })),
    [agents]
  );

  const qualityPct = Math.round(quality.value * 100);
  const characterList = React.useMemo(
    () => characters.map((c) => ({ id: c.id, name: c.name })),
    [characters]
  );

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[420px_1fr]">
      <Card>
        <CardContent>
          <PipelineForm onSubmit={onSubmit} pending={pending} />
        </CardContent>
      </Card>

      <div className="flex flex-col gap-6">
        <TheaterPanel
          phases={phases}
          currentPhase={currentPhase}
          agents={agentBubbleProps}
          quality={qualityPct}
          characters={characterList}
          debateMarker={debateMarker ?? undefined}
        />
        <ResultPanel story={resultStory} />
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
