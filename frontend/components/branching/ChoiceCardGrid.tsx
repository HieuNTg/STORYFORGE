"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { ChoiceCard } from "./ChoiceCard";

export interface ChoiceCardItem {
  id: string;
  title: string;
  summary?: string;
}

export interface ChoiceCardGridProps {
  choices: ChoiceCardItem[];
  onChoose: (id: string) => void;
  disabled?: boolean;
  className?: string;
}

/**
 * ChoiceCardGrid — responsive 1/2/3-col layout for branch choices.
 * Mobile: single column. Desktop: 2 cols at sm, 3 cols at lg when ≥3 choices.
 */
export function ChoiceCardGrid({
  choices,
  onChoose,
  disabled,
  className,
}: ChoiceCardGridProps) {
  const t = useTranslations("branching");
  if (choices.length === 0) {
    return (
      <p className="font-serif text-sm italic text-muted-foreground">
        {t("choice_next_empty")}
      </p>
    );
  }
  const cols =
    choices.length >= 3
      ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
      : "grid-cols-1 sm:grid-cols-2";
  return (
    <div className={cn("grid gap-3", cols, className)}>
      {choices.map((c) => (
        <ChoiceCard
          key={c.id}
          title={c.title}
          summary={c.summary}
          disabled={disabled}
          onSelect={() => onChoose(c.id)}
        />
      ))}
    </div>
  );
}
