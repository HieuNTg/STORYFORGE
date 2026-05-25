"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Trash2, ArrowRight, Plus, Bookmark } from "lucide-react";
import { EmptyState } from "@/components/common/EmptyState";

export interface BookmarkItem {
  id: string;
  label: string;
  created_at: string;
  node_id: string;
}

export interface BookmarksDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookmarks: BookmarkItem[];
  onGoto: (id: string) => void;
  onDelete: (id: string) => void;
  onAdd: (label: string) => void;
  className?: string;
}

function formatTs(iso: string): string {
  // Best-effort short locale time. Fall back to raw if invalid.
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function BookmarksDrawer({
  open,
  onOpenChange,
  bookmarks,
  onGoto,
  onDelete,
  onAdd,
  className,
}: BookmarksDrawerProps) {
  const t = useTranslations("branching");
  const [draft, setDraft] = React.useState("");

  function handleAdd() {
    const trimmed = draft.trim();
    if (!trimmed) return;
    onAdd(trimmed);
    setDraft("");
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className={cn("w-96 max-w-[90vw]", className)}>
        <SheetHeader>
          <SheetTitle>{t("bookmarks_title")}</SheetTitle>
          <SheetDescription>
            {t("bookmarks_desc")}
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-col gap-3 px-4">
          <div className="flex items-center gap-2">
            <Input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAdd();
                }
              }}
              placeholder={t("bookmarks_placeholder")}
              aria-label={t("bookmarks_aria_new")}
            />
            <Button
              type="button"
              variant="default"
              size="sm"
              onClick={handleAdd}
              disabled={!draft.trim()}
              aria-label={t("bookmarks_aria_add")}
            >
              <Plus />
              <span className="hidden sm:inline">{t("bookmarks_add_cta")}</span>
            </Button>
          </div>
        </div>

        <ScrollArea className="flex-1 px-2 pb-4">
          {bookmarks.length === 0 ? (
            <EmptyState
              icon={Bookmark}
              title={t("bookmarks_empty")}
              description={t("bookmarks_empty_desc")}
            />
          ) : (
            <ul className="flex flex-col gap-1 px-2">
              {bookmarks.map((b) => (
                <li
                  key={b.id}
                  className="flex items-center gap-2 rounded-md border border-transparent px-2 py-2 transition-colors hover:border-border hover:bg-muted/60"
                >
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="line-clamp-1 text-sm font-medium text-foreground">
                      {b.label}
                    </span>
                    <span className="text-xs tabular-nums text-muted-foreground">
                      {formatTs(b.created_at)}
                    </span>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onGoto(b.id)}
                    aria-label={t("bookmarks_goto")}
                    title={t("bookmarks_goto")}
                  >
                    <ArrowRight />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => onDelete(b.id)}
                    aria-label={t("bookmarks_delete_aria")}
                    title={t("bookmarks_delete")}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
