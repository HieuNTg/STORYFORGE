"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { RoleBadge } from "./RoleBadge";
import type { ForgeCharacter } from "@/types/story";

export interface CharacterListItemMeta {
  avatarUrl?: string | null;
  hasReferenceImage?: boolean;
}

export interface CharacterListProps {
  characters: ForgeCharacter[];
  selectedName: string | null;
  onSelect: (name: string) => void;
  profilesByName?: Map<string, CharacterListItemMeta>;
  className?: string;
}

/**
 * Pull initials from a Vietnamese / Chinese name.
 * "Lý Tiêu Dao" → "LD" ; "Diệp Vô Hằng" → "DH" ; single token → first 2 chars.
 */
function initialsOf(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  const first = parts[0][0] ?? "";
  const last = parts[parts.length - 1][0] ?? "";
  return (first + last).toUpperCase();
}

export function CharacterList({
  characters,
  selectedName,
  onSelect,
  profilesByName,
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
      <ul
        className={cn("space-y-1", className)}
        role="listbox"
        aria-label={t("title")}
      >
        {characters.map((c) => {
          const active = c.name === selectedName;
          const meta = profilesByName?.get(c.name);
          const hasImage = !!meta?.hasReferenceImage && !!meta?.avatarUrl;

          return (
            <li key={c.name}>
              <button
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => onSelect(c.name)}
                className={cn(
                  "group relative flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left text-sm transition",
                  active
                    ? "border-transparent bg-[color-mix(in_oklab,var(--accent)_10%,transparent)] before:absolute before:left-0 before:top-1/2 before:h-6 before:w-[3px] before:-translate-y-1/2 before:rounded-r before:bg-[var(--accent)]"
                    : "border-border/40 bg-background/30 hover:border-border hover:bg-muted/40",
                )}
              >
                <Avatar
                  size="lg"
                  className={cn(
                    "rounded-md after:rounded-md",
                    "ring-1 ring-border/60",
                  )}
                >
                  {hasImage ? (
                    <AvatarImage
                      src={meta!.avatarUrl!}
                      alt={t("portrait_alt", { name: c.name })}
                      className="rounded-md"
                    />
                  ) : null}
                  <AvatarFallback className="rounded-md text-xs font-medium text-[var(--accent)]">
                    {initialsOf(c.name)}
                  </AvatarFallback>
                </Avatar>

                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="truncate font-medium">{c.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <RoleBadge role={c.role} className="text-[10px]" />
                  </div>
                </div>

                <span
                  title={
                    hasImage
                      ? t("image_status_ready")
                      : t("image_status_missing")
                  }
                  aria-label={
                    hasImage
                      ? t("image_status_ready")
                      : t("image_status_missing")
                  }
                  className={cn(
                    "h-2 w-2 shrink-0 rounded-full",
                    hasImage
                      ? "bg-emerald-400"
                      : "border border-muted-foreground/60 bg-transparent",
                  )}
                />
              </button>
            </li>
          );
        })}
      </ul>
  );
}
