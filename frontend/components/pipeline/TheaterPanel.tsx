"use client";

import * as React from "react";
import { Users, X, Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { PhaseTimeline, type Phase, type PhaseSubInfo } from "./PhaseTimeline";
import { AgentBubble, type AgentBubbleProps } from "./AgentBubble";
import { QualityGauge } from "./QualityGauge";
import { EmptyState } from "@/components/common/EmptyState";

export interface TheaterCharacter {
  id: string;
  name: string;
}

export interface TheaterPanelProps {
  phases?: Phase[];
  currentPhase?: number;
  /** Per-phase substep info keyed by phase index. */
  phaseSubInfo?: Record<number, PhaseSubInfo>;
  agents: AgentBubbleProps[];
  quality?: number;
  /** Quality layer (1 or 2) for the gauge caption. */
  qualityLayer?: number;
  /** Epoch ms of latest quality update for "vừa cập nhật" caption. */
  qualityUpdatedAt?: number;
  characters?: TheaterCharacter[];
  debateMarker?: string;
  /** Epoch ms when generation started; drives the elapsed timer. */
  startedAt?: number;
  /** Total expected duration in seconds for ETA; falls back to a rough estimate. */
  etaSeconds?: number;
  /** Set to true while the pipeline is running to show timer + cancel. */
  running?: boolean;
  /** Optional cancel callback; renders the cancel button when provided. */
  onCancel?: () => void;
  className?: string;
}

/** Render an elapsed mm:ss timer that ticks once per second. */
function useElapsedSeconds(startedAt?: number, running?: boolean): number | null {
  const [now, setNow] = React.useState<number>(() => Date.now());
  React.useEffect(() => {
    if (!startedAt || !running) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [startedAt, running]);
  if (!startedAt) return null;
  return Math.max(0, Math.floor((now - startedAt) / 1000));
}

function formatMmSs(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function TheaterPanel({
  phases,
  currentPhase,
  phaseSubInfo,
  agents,
  quality,
  qualityLayer,
  qualityUpdatedAt,
  characters,
  debateMarker,
  startedAt,
  etaSeconds,
  running,
  onCancel,
  className,
}: TheaterPanelProps) {
  const hasAgents = agents.length > 0;
  const elapsed = useElapsedSeconds(startedAt, running);
  const showStatusStrip = Boolean(running || startedAt);
  const remaining =
    typeof etaSeconds === "number" && elapsed !== null
      ? Math.max(0, etaSeconds - elapsed)
      : null;

  // Sticky scroll: anchor to bottom while new bubbles stream in, but let the
  // user scroll up without being fought.
  const scrollWrapRef = React.useRef<HTMLDivElement | null>(null);
  const stickRef = React.useRef(true);
  const findViewport = React.useCallback((): HTMLElement | null => {
    return (scrollWrapRef.current?.querySelector(
      '[data-slot="scroll-area-viewport"]',
    ) as HTMLElement | null) ?? null;
  }, []);
  React.useEffect(() => {
    const el = findViewport();
    if (!el) return;
    const onScroll = () => {
      const slack = 24;
      stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < slack;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [findViewport, hasAgents]);
  const lastPartial = agents[agents.length - 1]?.partial;
  React.useEffect(() => {
    if (!stickRef.current) return;
    const el = findViewport();
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [agents.length, lastPartial, findViewport]);

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {phases && phases.length > 0 ? (
        <Card>
          <CardContent>
            <PhaseTimeline
              phases={phases}
              current={currentPhase}
              subInfo={phaseSubInfo}
            />
            {showStatusStrip && (
              <div className="mt-3 flex items-center justify-between gap-3 border-t pt-3 text-xs text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Clock className="size-3.5" aria-hidden />
                  <span aria-live="polite">
                    {elapsed !== null ? `Đã chạy ${formatMmSs(elapsed)}` : "Chuẩn bị…"}
                    {remaining !== null
                      ? ` · còn ~${formatMmSs(remaining)}`
                      : ""}
                  </span>
                </div>
                {onCancel && running ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-7 gap-1.5 px-2 text-xs"
                    onClick={onCancel}
                  >
                    <X className="size-3.5" aria-hidden />
                    Huỷ
                  </Button>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <CardTitle>Hội thoại tác giả</CardTitle>
            {debateMarker ? (
              <Badge variant="outline" className="border-accent/30 text-accent-foreground">
                {debateMarker}
              </Badge>
            ) : null}
          </CardHeader>
          <CardContent>
            {hasAgents ? (
              <div ref={scrollWrapRef}>
                <ScrollArea className="h-[440px] pr-2">
                  {/* SSE-driven agent stream: aria-live=polite so screen readers
                   * announce each new author turn without stealing focus
                   * (WCAG 4.1.3 Status Messages). */}
                  <div
                    className="flex flex-col gap-2.5"
                    role="log"
                    aria-live="polite"
                    aria-label="Hội thoại tác giả đang diễn ra"
                  >
                    {agents.map((agent, idx) => (
                      <AgentBubble key={`${agent.name}-${agent.turn ?? idx}`} {...agent} />
                    ))}
                  </div>
                </ScrollArea>
              </div>
            ) : running ? (
              // Skeleton placeholders cover the gap between "Start" click and
              // the first sniffer-matching log so the panel never looks frozen.
              <div className="flex flex-col gap-2.5" aria-hidden>
                <Skeleton className="h-16 w-full rounded-md" />
                <Skeleton className="h-12 w-11/12 rounded-md" />
                <Skeleton className="h-12 w-10/12 rounded-md" />
              </div>
            ) : (
              <EmptyState
                icon={Users}
                title="Đang chuẩn bị..."
                description="Các tác giả ảo sẽ xuất hiện khi quá trình sáng tác bắt đầu."
              />
            )}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>Chỉ số chất lượng</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-center pb-4">
              <QualityGauge
                value={quality ?? 0}
                layer={qualityLayer}
                updatedAt={qualityUpdatedAt}
              />
            </CardContent>
          </Card>

          {characters && characters.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Nhân vật</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-wrap gap-1.5">
                  {characters.map((c) => (
                    <li key={c.id}>
                      <Badge variant="secondary">{c.name}</Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
