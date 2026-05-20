"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface StatTileProps {
  label: string;
  value: string;
  hint?: string;
  icon?: React.ReactNode;
  className?: string;
}

export function StatTile({ label, value, hint, icon, className }: StatTileProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 rounded-xl border border-accent/40 bg-card/60 p-4 shadow-sm",
        "transition-colors hover:border-accent",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2 text-xs uppercase tracking-wider text-muted-foreground">
        <span className="font-mono">{label}</span>
        {icon ? <span className="text-accent">{icon}</span> : null}
      </div>
      <div className="font-serif text-2xl text-foreground">{value}</div>
      {hint ? (
        <div className="text-xs text-muted-foreground">{hint}</div>
      ) : null}
    </div>
  );
}
