"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { RoleBadge } from "./RoleBadge";
import type { ForgeCharacter } from "@/types/story";

export interface CharacterListProps {
  characters: ForgeCharacter[];
  selectedName: string | null;
  onSelect: (name: string) => void;
  className?: string;
}

export function CharacterList({
  characters,
  selectedName,
  onSelect,
  className,
}: CharacterListProps) {
  const t = useTranslations("characters");

  if (!characters.length) {
    return (
      <div
        className={cn(
          "rounded-xl border border-dashed border-border/60 p-6 text-center text-sm text-muted-foreground",
          className,
        )}
      >
        <p className="font-medium">{t("empty")}</p>
        <p className="mt-1 text-xs">{t("empty_hint")}</p>
      </div>
    );
  }

  return (
    <ul className={cn("space-y-1", className)} role="listbox" aria-label={t("title")}>
      {characters.map((c) => {
        const active = c.name === selectedName;
        return (
          <li key={c.name}>
            <button
              type="button"
              role="option"
              aria-selected={active}
              onClick={() => onSelect(c.name)}
              className={cn(
                "flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left text-sm transition",
                active
                  ? "border-primary/50 bg-primary/10"
                  : "border-border/40 bg-background/30 hover:border-border hover:bg-muted/40",
              )}
            >
              <span className="min-w-0 flex-1 truncate font-medium">{c.name}</span>
              <RoleBadge role={c.role} />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
