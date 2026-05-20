"use client";

import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import type { ForgeCharacter } from "@/types/story";

export function NarrativePanels({
  character,
  className,
}: {
  character: ForgeCharacter;
  className?: string;
}) {
  const t = useTranslations("characters");

  const items: { label: string; body: string }[] = [
    { label: t("description_label"), body: character.description },
    { label: t("backstory_label"), body: character.backstory },
    { label: t("secret_label"), body: character.secret },
    { label: t("conflict_label"), body: character.conflict },
  ];

  return (
    <dl className={cn("space-y-3", className)}>
      {items.map((it) => (
        <div key={it.label} className="rounded-lg border border-border/40 bg-background/40 p-3">
          <dt className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            {it.label}
          </dt>
          <dd className="mt-1 text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap">
            {it.body || "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}
