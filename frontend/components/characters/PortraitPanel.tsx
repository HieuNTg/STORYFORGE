"use client";

import { useTranslations } from "next-intl";
import { User } from "lucide-react";
import { cn } from "@/lib/utils";

export function PortraitPanel({
  name,
  src,
  className,
}: {
  name: string;
  src?: string | null;
  className?: string;
}) {
  const t = useTranslations("characters");
  return (
    <div
      className={cn(
        "relative aspect-square w-full overflow-hidden rounded-xl border border-border/60 bg-gradient-to-br from-background/60 to-muted/30",
        className,
      )}
    >
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={t("portrait_alt", { name })}
          className="absolute inset-0 h-full w-full object-cover"
        />
      ) : (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground">
          <User className="size-10 opacity-50" aria-hidden />
          <span className="text-xs">{t("portrait_placeholder")}</span>
        </div>
      )}
    </div>
  );
}
