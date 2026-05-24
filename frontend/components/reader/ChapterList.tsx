"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTrigger, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { List } from "lucide-react";

export interface ChapterListItem {
  id: string;
  title: string;
  word_count?: number;
}

export interface ChapterListProps {
  chapters: ChapterListItem[];
  currentChapter: number;
  onSelect: (index: number) => void;
  className?: string;
}

/**
 * Renders the chapter rail. Each item shows index, title, and word count.
 * The current chapter gets an accent left-border + raised text weight.
 */
function ChapterListInner({ chapters, currentChapter, onSelect }: ChapterListProps) {
  const t = useTranslations("reader");
  return (
    <ol className="flex flex-col gap-px py-1" aria-label={t("select_chapter")}>
      {chapters.map((ch, idx) => {
        const isCurrent = idx === currentChapter;
        return (
          <li key={ch.id}>
            <button
              type="button"
              onClick={() => onSelect(idx)}
              aria-current={isCurrent ? "true" : undefined}
              className={cn(
                "group flex w-full items-start gap-3 rounded-md border-l-2 px-3 py-2 text-left text-sm transition-colors duration-[var(--duration-fast)] ease-[var(--ease-out)]",
                isCurrent
                  ? "border-accent bg-muted text-foreground"
                  : "border-transparent text-muted-foreground hover:border-border hover:bg-muted/60 hover:text-foreground"
              )}
            >
              <span
                className={cn(
                  "shrink-0 tabular-nums",
                  isCurrent ? "font-medium text-foreground" : "text-muted-foreground"
                )}
              >
                {String(idx + 1).padStart(2, "0")}
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span
                  className={cn(
                    "line-clamp-2 leading-snug",
                    isCurrent && "font-medium"
                  )}
                >
                  {ch.title}
                </span>
                {typeof ch.word_count === "number" ? (
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {t("word_count", { count: ch.word_count })}
                  </span>
                ) : null}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

export function ChapterList(props: ChapterListProps) {
  const t = useTranslations("reader");
  const { className, chapters, currentChapter } = props;
  const currentTitle = chapters[currentChapter]?.title ?? t("select_chapter");

  return (
    <>
      {/* Mobile: trigger Sheet */}
      <div className={cn("lg:hidden", className)}>
        <Sheet>
          <SheetTrigger
            render={
              <Button variant="outline" size="sm" className="w-full justify-start gap-2">
                <List />
                <span className="truncate">
                  {`${t("select_chapter")} ${currentChapter + 1} — ${currentTitle}`}
                </span>
              </Button>
            }
          />
          <SheetContent side="left" className="w-80 max-w-[85vw]">
            <SheetHeader>
              <SheetTitle>{t("chapter_list_title")}</SheetTitle>
            </SheetHeader>
            <ScrollArea className="flex-1 px-2">
              <ChapterListInner {...props} />
            </ScrollArea>
          </SheetContent>
        </Sheet>
      </div>

      {/* Desktop rail */}
      <div className={cn("hidden lg:block", className)}>
        <div className="sticky top-4 rounded-xl border bg-card">
          <div className="border-b px-4 py-3">
            <h2 className="text-sm font-medium text-foreground">{t("select_chapter")}</h2>
            <p className="text-xs text-muted-foreground tabular-nums">
              {t("chapters_count", { count: chapters.length })}
            </p>
          </div>
          <ScrollArea className="max-h-[calc(100vh-12rem)] px-1.5 py-1">
            <ChapterListInner {...props} />
          </ScrollArea>
        </div>
      </div>
    </>
  );
}
