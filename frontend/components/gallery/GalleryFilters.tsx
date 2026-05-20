"use client";

/**
 * GalleryFilters — final visual treatment (Phase 4 UI design).
 *
 * Layout:
 *   - Genre: shadcn Select (can grow with backend taxonomy)
 *   - Length: segmented-control pills (Tất cả / Ngắn / Vừa / Dài). Active pill
 *     uses `--primary` (filled), inactive uses `--secondary`. Matches the
 *     "toggle pills" register requested in the Phase 4 brief.
 *   - Sticky top bar w/ subtle backdrop blur, matching LibraryToolbar.
 *
 * Values are URL-driven via nuqs on the page; this component is
 * presentation-only. API contract preserved from the FE-dev stub:
 *   { genre, length, onGenreChange, onLengthChange, genreOptions, totalLabel }
 * — using "" as the "no filter" empty value (mapped to an `__all__` sentinel
 * internally because Base UI Select rejects empty-string values).
 */

import * as React from "react";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export interface GalleryFiltersProps {
  genre: string;
  length: string;
  onGenreChange: (v: string) => void;
  onLengthChange: (v: string) => void;
  genreOptions: string[];
  /** Trailing badge — e.g. "24 mục". Caller formats. */
  totalLabel?: string;
  className?: string;
}

const LENGTH_PILLS: Array<{ value: string; label: string }> = [
  { value: "", label: "Tất cả" },
  { value: "short", label: "Ngắn" },
  { value: "medium", label: "Vừa" },
  { value: "long", label: "Dài" },
];

const ALL = "__all__";

export function GalleryFilters({
  genre,
  length,
  onGenreChange,
  onLengthChange,
  genreOptions,
  totalLabel,
  className,
}: GalleryFiltersProps) {
  const hasFilter = !!genre || !!length;

  return (
    <div
      className={cn(
        "sticky top-0 z-10 flex flex-col gap-3 border-b border-border/60 bg-background/95 py-3 backdrop-blur",
        "sm:flex-row sm:flex-wrap sm:items-center sm:gap-3",
        className,
      )}
    >
      {/* Genre: dropdown (taxonomy may grow). */}
      <Select
        value={genre || ALL}
        onValueChange={(v: unknown) =>
          onGenreChange(String(v) === ALL ? "" : String(v))
        }
      >
        <SelectTrigger
          size="sm"
          className="min-w-40"
          aria-label="Lọc theo thể loại"
        >
          <SelectValue placeholder="Thể loại" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>Tất cả thể loại</SelectItem>
          {genreOptions.map((g) => (
            <SelectItem key={g} value={g}>
              {g}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* Length: segmented-control toggle pills. */}
      <div
        role="radiogroup"
        aria-label="Lọc theo độ dài"
        className="inline-flex items-center gap-0.5 rounded-md border border-border/60 bg-secondary/60 p-0.5"
      >
        {LENGTH_PILLS.map((p) => {
          const active = (length || "") === p.value;
          return (
            <button
              key={p.value || "all"}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onLengthChange(p.value)}
              className={cn(
                "rounded-[0.3125rem] px-2.5 py-1 text-xs font-medium",
                "transition-colors duration-[var(--motion-fast)] ease-[var(--ease-out)]",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
                active
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-background hover:text-foreground",
              )}
            >
              {p.label}
            </button>
          );
        })}
      </div>

      {hasFilter ? (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            onGenreChange("");
            onLengthChange("");
          }}
          aria-label="Xoá bộ lọc"
        >
          <X className="size-3.5" aria-hidden />
          Xoá lọc
        </Button>
      ) : null}

      {totalLabel ? (
        <Badge variant="secondary" className="ml-auto tabular-nums">
          {totalLabel}
        </Badge>
      ) : null}
    </div>
  );
}
