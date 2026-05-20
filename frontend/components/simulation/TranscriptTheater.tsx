"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { useSimulationStore } from "@/stores/simulation-store";
import { TurnBubble } from "./TurnBubble";

export function TranscriptTheater() {
  const t = useTranslations("simulation");
  const logs = useSimulationStore((s) => s.logs);
  const cursor = useSimulationStore((s) => s.cursor);
  const playing = useSimulationStore((s) => s.playing);
  const stepForward = useSimulationStore((s) => s.stepForward);
  const pause = useSimulationStore((s) => s.pause);
  const endRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const { cursor: cur, logs: ls } = useSimulationStore.getState();
      if (cur >= ls.length - 1) {
        pause();
        return;
      }
      stepForward();
    }, 1500);
    return () => window.clearInterval(id);
  }, [playing, stepForward, pause]);

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [logs.length]);

  if (logs.length === 0) {
    return (
      <div className="flex h-full min-h-[320px] items-center justify-center rounded-xl border border-dashed border-border/60 p-8 text-sm text-muted-foreground">
        {t("transcript_empty")}
      </div>
    );
  }

  return (
    <section
      className="flex h-full max-h-[70vh] flex-col gap-3 overflow-y-auto rounded-xl border border-border/40 bg-background/40 p-4"
      aria-label={t("transcript")}
    >
      {logs.map((turn, idx) => (
        <TurnBubble key={turn.id} turn={turn} active={idx === cursor} />
      ))}
      <div ref={endRef} aria-hidden="true" />
    </section>
  );
}
