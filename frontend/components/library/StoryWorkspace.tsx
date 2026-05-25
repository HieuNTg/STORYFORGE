"use client";

/**
 * StoryWorkspace — single-story detail panel.
 *
 * Shows cover + meta (genre/setting/tone/character-count), chapters list with
 * `ĐK`/`Ch` badges + status pills, and Export JSON / Delete actions.
 * Delete opens a confirm dialog (no AlertDialog primitive in repo yet).
 */

import * as React from "react";
import {
  BookOpen,
  ChevronDown,
  Download,
  Trash2,
  Users,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import {
  exportStory,
  exportStoryToFormat,
  type LibraryExportFormat,
} from "@/lib/library/json-io";
import type { Story, StoryChapter } from "@/types/story";
import { displayStoryTitle } from "@/lib/library/display-helpers";

export interface StoryWorkspaceProps {
  story: Story;
  onDelete: (id: string) => void;
  onOpenReader?: (id: string) => void;
  onOpenContinue?: (id: string) => void;
  className?: string;
}

const STATUS_KEY: Record<StoryChapter["status"], string> = {
  draft: "status_draft",
  ready: "status_ready",
  enhanced: "status_enhanced",
};

const STATUS_VARIANT: Record<StoryChapter["status"], "outline" | "secondary" | "default"> = {
  draft: "outline",
  ready: "secondary",
  enhanced: "default",
};

export function StoryWorkspace({
  story,
  onDelete,
  onOpenReader,
  onOpenContinue,
  className,
}: StoryWorkspaceProps) {
  const t = useTranslations("library");
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [exportingFmt, setExportingFmt] = React.useState<LibraryExportFormat | null>(null);

  const handleExport = () => {
    try {
      exportStory(story);
      toast.success(t("exported"));
    } catch (err) {
      toast.error(t("export_failed"), {
        description: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const handleServerExport = async (fmt: LibraryExportFormat) => {
    setExportingFmt(fmt);
    try {
      await exportStoryToFormat(story, fmt);
      toast.success(t("exported_format", { format: fmt.toUpperCase() }));
    } catch (err) {
      toast.error(t("export_format_failed", { format: fmt.toUpperCase() }), {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setExportingFmt(null);
    }
  };

  const handleOpenReader = React.useCallback(() => {
    onOpenReader?.(story.id);
  }, [onOpenReader, story.id]);

  const handleOpenContinue = React.useCallback(() => {
    onOpenContinue?.(story.id);
  }, [onOpenContinue, story.id]);

  return (
    <aside
      className={cn(
        "flex h-full flex-col gap-4 rounded-xl border border-border/60 bg-card/70 p-4 shadow-sm backdrop-blur",
        className,
      )}
      aria-label={t("story_detail_label", { title: displayStoryTitle(story, t("untitled_story")) })}
    >
      <div className="relative aspect-[3/4] overflow-hidden rounded-lg bg-muted">
        {story.coverUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={story.coverUrl}
            alt=""
            className="size-full object-cover"
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="flex size-full items-center justify-center bg-gradient-to-br from-muted to-muted/60 text-muted-foreground">
            <BookOpen className="size-12" />
          </div>
        )}
        {story.genre ? (
          <Badge
            variant="outline"
            className="absolute top-2 left-2 border-[var(--color-accent,#C5A47E)]/40 bg-[var(--color-accent,#C5A47E)]/15 text-[var(--color-accent,#C5A47E)] backdrop-blur-sm"
          >
            {story.genre}
          </Badge>
        ) : null}
      </div>

      <header className="space-y-1">
        <h2 className="text-lg font-semibold leading-tight">{displayStoryTitle(story, t("untitled_story"))}</h2>
        {story.description ? (
          <p className="line-clamp-3 text-sm text-muted-foreground">
            {story.description}
          </p>
        ) : null}
      </header>

      <dl className="grid grid-cols-2 gap-2 text-xs">
        <Meta label={t("setting")} value={story.setting || "—"} />
        <Meta label={t("tone")} value={story.tone || "—"} />
        <Meta
          label={t("characters")}
          value={
            <span className="inline-flex items-center gap-1">
              <Users className="size-3" aria-hidden />
              {story.characters.length}
            </span>
          }
        />
        <Meta
          label={t("chapters")}
          value={
            <span className="inline-flex items-center gap-1">
              <FileText className="size-3" aria-hidden />
              {story.chapters.length}
            </span>
          }
        />
      </dl>

      <div className="flex-1 min-h-0">
        <h3 className="mb-1.5 text-xs font-medium text-muted-foreground">
          {t("chapter_list")}
        </h3>
        {story.chapters.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("no_chapters")}</p>
        ) : (
          <ScrollArea className="h-full max-h-64 rounded-md border border-border/60">
            <ul role="list" className="divide-y divide-border/40">
              {story.chapters.map((ch, i) => (
                <li key={ch.id} className="flex items-center gap-2 p-2 text-xs">
                  <Badge
                    variant={ch.badge === "ĐK" ? "default" : "outline"}
                    className={cn(
                      "shrink-0 font-mono",
                      ch.badge === "ĐK" &&
                        "bg-[var(--color-accent,#C5A47E)]/15 text-[var(--color-accent,#C5A47E)] border-[var(--color-accent,#C5A47E)]/40",
                    )}
                  >
                    {ch.badge}
                    {i + 1}
                  </Badge>
                  <span className="line-clamp-1 flex-1">{ch.title}</span>
                  <Badge variant={STATUS_VARIANT[ch.status]} className="shrink-0">
                    {t(STATUS_KEY[ch.status])}
                  </Badge>
                </li>
              ))}
            </ul>
          </ScrollArea>
        )}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Button type="button" onClick={handleOpenReader} className="gap-1.5">
          <BookOpen className="size-4" aria-hidden />
          {t("read")}
        </Button>
        <Button type="button" variant="secondary" onClick={handleOpenContinue} className="gap-1.5">
          <ChevronDown className="size-4 rotate-[-90deg]" aria-hidden />
          {t("continue")}
        </Button>
      </div>

      <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button
                type="button"
                variant="outline"
                disabled={exportingFmt !== null}
                className="flex-1 gap-1.5"
              />
            }
          >
            <Download className="size-4" aria-hidden />
            {exportingFmt ? t("exporting", { format: exportingFmt.toUpperCase() }) : t("export_menu")}
            <ChevronDown className="ml-auto size-4" aria-hidden />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-44">
            <DropdownMenuGroup>
              <DropdownMenuLabel>{t("choose_format")}</DropdownMenuLabel>
              <DropdownMenuItem onClick={handleExport}>JSON</DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={() => void handleServerExport("docx")}>
                DOCX / Word
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => void handleServerExport("pdf")}>
                PDF
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => void handleServerExport("epub")}>
                EPUB
              </DropdownMenuItem>
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
        <Button
          type="button"
          variant="outline"
          onClick={() => setConfirmOpen(true)}
          className="text-destructive hover:bg-destructive/10"
          aria-label={t("delete")}
        >
          <Trash2 className="size-4" aria-hidden />
        </Button>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("delete_confirm_title")}</DialogTitle>
            <DialogDescription>{t("delete_confirm_body")}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              {t("cancel")}
            </DialogClose>
            <Button
              type="button"
              variant="destructive"
              onClick={() => {
                onDelete(story.id);
                setConfirmOpen(false);
                toast.success(t("deleted"));
              }}
            >
              {t("delete_action")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  );
}

function Meta({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-0.5 text-foreground">{value}</dd>
    </div>
  );
}

