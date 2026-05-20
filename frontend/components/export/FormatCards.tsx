"use client";

import * as React from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export interface ExportFormatOption {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
  recommended?: boolean;
}

export interface FormatCardsProps {
  formats: ExportFormatOption[];
  selected?: string;
  onSelect: (id: string) => void;
  className?: string;
}

/**
 * Grid of selectable export-format cards.
 * 1 column on mobile, 2 on tablet, 4 on desktop.
 */
export function FormatCards({
  formats,
  selected,
  onSelect,
  className,
}: FormatCardsProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4",
        className,
      )}
    >
      {formats.map((format) => {
        const Icon = format.icon;
        const isSelected = selected === format.id;
        return (
          <button
            key={format.id}
            type="button"
            aria-pressed={isSelected}
            onClick={() => onSelect(format.id)}
            className={cn(
              "group relative flex flex-col items-start gap-2 rounded-xl bg-card p-4 text-left ring-1 ring-foreground/10 transition-[transform,box-shadow,border-color] duration-150 ease-out outline-none hover:-translate-y-px hover:ring-foreground/20 focus-visible:ring-2 focus-visible:ring-ring",
              isSelected && "ring-2 ring-accent hover:ring-accent",
            )}
          >
            {format.recommended ? (
              <Badge
                variant="outline"
                className="absolute right-3 top-3 border-accent text-accent"
              >
                Đề xuất
              </Badge>
            ) : null}
            <span
              aria-hidden
              className={cn(
                "flex size-9 items-center justify-center rounded-lg bg-muted text-foreground/80",
                isSelected && "bg-accent/10 text-accent",
              )}
            >
              <Icon className="size-5" />
            </span>
            <span className="text-sm font-medium text-foreground">
              {format.label}
            </span>
            <span className="line-clamp-1 text-xs text-muted-foreground">
              {format.description}
            </span>
          </button>
        );
      })}
    </div>
  );
}
