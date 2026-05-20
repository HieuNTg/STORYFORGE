"use client";

import { motion, useReducedMotion } from "motion/react";
import type { TranscriptTurn } from "@/types/story";

interface TurnBubbleProps {
  turn: TranscriptTurn;
  active: boolean;
  delay?: number;
}

export function TurnBubble({ turn, active, delay = 0 }: TurnBubbleProps) {
  const reduce = useReducedMotion();
  const motionProps = reduce
    ? {}
    : {
        initial: { opacity: 0, y: 6 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0.3, delay, ease: "easeOut" as const },
      };

  return (
    <motion.article
      {...motionProps}
      data-active={active}
      className="rounded-xl border border-border/50 bg-card/60 p-4 transition-colors data-[active=true]:border-primary/60 data-[active=true]:bg-card"
    >
      <header className="mb-2 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold">{turn.senderName}</h4>
        {turn.emotion ? (
          <span className="rounded-full border border-border/60 px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
            {turn.emotion}
          </span>
        ) : null}
      </header>
      {turn.actionDetails ? (
        <p className="mb-1 text-xs italic text-muted-foreground">
          *{turn.actionDetails}*
        </p>
      ) : null}
      {turn.speech ? (
        <p className="text-sm leading-relaxed">« {turn.speech} »</p>
      ) : null}
    </motion.article>
  );
}
