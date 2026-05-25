"use client";

import { useLocale, useTranslations } from "next-intl";
import { Languages } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

const LOCALES = [
  { code: "vi", label: "Tiếng Việt" },
  { code: "en", label: "English" },
] as const;

function persistLocale(locale: string) {
  // 1 year, root path. The static app also mirrors this in localStorage so the
  // client provider can switch without requiring a server-rendered locale.
  const maxAge = 60 * 60 * 24 * 365;
  document.cookie = `NEXT_LOCALE=${encodeURIComponent(locale)}; Path=/; Max-Age=${maxAge}; SameSite=Lax`;
  window.localStorage.setItem("storyforge_locale", locale);
}

export function LocaleSwitcher() {
  const current = useLocale();
  const t = useTranslations("shell");

  function pick(code: string) {
    if (code === current) return;
    persistLocale(code);
    window.dispatchEvent(new CustomEvent("storyforge:locale", { detail: code }));
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        type="button"
        aria-label={t("locale_switch")}
        className={cn(buttonVariants({ variant: "ghost", size: "icon" }))}
      >
        <Languages className="size-4" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {LOCALES.map((l) => (
          <DropdownMenuItem
            key={l.code}
            onClick={() => pick(l.code)}
            aria-current={l.code === current ? "true" : undefined}
          >
            <span className="font-mono text-xs uppercase">{l.code}</span>
            <span className="text-muted-foreground">{l.label}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
