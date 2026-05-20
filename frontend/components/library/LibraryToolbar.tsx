"use client";

import * as React from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

export type LibrarySort = "recent" | "title" | "length";

export interface LibraryToolbarProps {
  q: string;
  onQChange: (v: string) => void;
  sort: LibrarySort;
  onSortChange: (s: LibrarySort) => void;
  count?: number;
  className?: string;
}

const SORT_LABEL: Record<LibrarySort, string> = {
  recent: "Mới nhất",
  title: "Theo tên",
  length: "Theo độ dài",
};

export function LibraryToolbar({
  q,
  onQChange,
  sort,
  onSortChange,
  count,
  className,
}: LibraryToolbarProps) {
  return (
    <div
      className={cn(
        "sticky top-0 z-10 flex flex-col gap-2 border-b border-border/60 bg-background/95 py-3 backdrop-blur sm:flex-row sm:items-center sm:gap-3",
        className
      )}
    >
      <div className="relative flex-1">
        <Search
          aria-hidden
          className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          type="search"
          value={q}
          onChange={(e) => onQChange(e.target.value)}
          placeholder="Tìm theo tên truyện..."
          aria-label="Tìm truyện"
          className="pl-8"
        />
      </div>

      <div className="flex items-center gap-2">
        <Select
          value={sort}
          onValueChange={(v: unknown) => onSortChange(v as LibrarySort)}
        >
          <SelectTrigger aria-label="Sắp xếp">
            <SelectValue placeholder={SORT_LABEL[sort]} />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="recent">{SORT_LABEL.recent}</SelectItem>
            <SelectItem value="title">{SORT_LABEL.title}</SelectItem>
            <SelectItem value="length">{SORT_LABEL.length}</SelectItem>
          </SelectContent>
        </Select>

        {typeof count === "number" ? (
          <Badge variant="secondary" className="tabular-nums">
            {new Intl.NumberFormat("vi-VN").format(count)} truyện
          </Badge>
        ) : null}
      </div>
    </div>
  );
}
