"use client";

import * as React from "react";
import { Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { PhaseTimeline, type Phase } from "./PhaseTimeline";
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
  agents: AgentBubbleProps[];
  quality?: number;
  characters?: TheaterCharacter[];
  debateMarker?: string;
  className?: string;
}

export function TheaterPanel({
  phases,
  currentPhase,
  agents,
  quality,
  characters,
  debateMarker,
  className,
}: TheaterPanelProps) {
  const hasAgents = agents.length > 0;

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {phases && phases.length > 0 ? (
        <Card>
          <CardContent>
            <PhaseTimeline phases={phases} current={currentPhase} />
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
              <QualityGauge value={quality ?? 0} />
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
