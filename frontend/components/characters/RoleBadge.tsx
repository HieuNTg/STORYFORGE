"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { ForgeRole } from "@/types/story";

const ROLE_TONE: Record<ForgeRole, string> = {
  protagonist: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  antagonist: "border-rose-500/40 bg-rose-500/10 text-rose-300",
  rival: "border-amber-500/40 bg-amber-500/10 text-amber-300",
  supporting: "border-sky-500/40 bg-sky-500/10 text-sky-300",
};

export function RoleBadge({
  role,
  className,
}: {
  role: ForgeRole;
  className?: string;
}) {
  const t = useTranslations("roles");
  return (
    <Badge
      variant="outline"
      className={cn("text-[10px] uppercase tracking-wider", ROLE_TONE[role], className)}
    >
      {t(role)}
    </Badge>
  );
}
