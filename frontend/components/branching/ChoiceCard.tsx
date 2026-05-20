"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * ChoiceCard — large gold-bordered card for a single branch choice.
 *
 * Visual contract (Phase 4 / storyforge-ai parity):
 *   - Min-height 96px, rounded-xl, gold rule + sepia hover wash
 *   - Title in serif (Cormorant Garamond fallback)
 *   - Optional 2-line summary in muted serif
 *   - Whole card is the button — keyboard activatable
 */
export interface ChoiceCardProps {
  title: string;
  summary?: string;
  disabled?: boolean;
  onSelect: () => void;
  className?: string;
}

export function ChoiceCard({
  title,
  summary,
  disabled,
  onSelect,
  className,
}: ChoiceCardProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "group flex w-full flex-col items-start gap-1.5 rounded-xl border px-5 py-4 text-left",
        "border-[color:var(--reader-rule,var(--border))] bg-card text-card-foreground",
        "min-h-[96px] transition-colors duration-[var(--duration-fast)] ease-[var(--ease-out)]",
        "hover:border-accent hover:bg-accent/5",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    >
      <span className="font-serif text-base font-medium leading-snug text-foreground">
        {title}
      </span>
      {summary ? (
        <span className="line-clamp-2 font-serif text-sm leading-relaxed text-muted-foreground">
          {summary}
        </span>
      ) : null}
    </button>
  );
}
