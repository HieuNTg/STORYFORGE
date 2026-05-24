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
  Download,
  Trash2,
  Users,
  FileText,
} from "lucide-react";
import { toast } from "sonner";
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
import { cn } from "@/lib/utils";
import {
  exportStory,
  exportStoryToFormat,
  type LibraryExportFormat,
} from "@/lib/library/json-io";
import type { Story, StoryChapter } from "@/types/story";

export interface StoryWorkspaceProps {
  story: Story;
  onDelete: (id: string) => void;
  className?: string;
}

const STATUS_LABEL: Record<StoryChapter["status"], string> = {
  draft: "Bản nháp",
  ready: "Sẵn sàng",
  enhanced: "Đã tinh chỉnh",
};

const STATUS_VARIANT: Record<StoryChapter["status"], "outline" | "secondary" | "default"> = {
  draft: "outline",
  ready: "secondary",
  enhanced: "default",
};

export function StoryWorkspace({
  story,
  onDelete,
  className,
}: StoryWorkspaceProps) {
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [exportingFmt, setExportingFmt] = React.useState<LibraryExportFormat | null>(null);

  const handleExport = () => {
    try {
      exportStory(story);
      toast.success("Đã xuất JSON");
    } catch (err) {
      toast.error("Xuất thất bại", {
        description: err instanceof Error ? err.message : String(err),
      });
    }
  };

  const handleServerExport = async (fmt: LibraryExportFormat) => {
    setExportingFmt(fmt);
    try {
      await exportStoryToFormat(story, fmt);
      toast.success(`Đã xuất ${fmt.toUpperCase()}`);
    } catch (err) {
      toast.error(`Xuất ${fmt.toUpperCase()} thất bại`, {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setExportingFmt(null);
    }
  };

  return (
    <aside
      className={cn(
        "flex h-full flex-col gap-4 rounded-xl border border-border/60 bg-card/70 p-4 shadow-sm backdrop-blur",
        className,
      )}
      aria-label={`Chi tiết truyện ${story.title}`}
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
        <h2 className="text-lg font-semibold leading-tight">{story.title}</h2>
        {story.description ? (
          <p className="line-clamp-3 text-sm text-muted-foreground">
            {story.description}
          </p>
        ) : null}
      </header>

      <dl className="grid grid-cols-2 gap-2 text-xs">
        <Meta label="Bối cảnh" value={story.setting || "—"} />
        <Meta label="Tông giọng" value={story.tone || "—"} />
        <Meta
          label="Nhân vật"
          value={
            <span className="inline-flex items-center gap-1">
              <Users className="size-3" aria-hidden />
              {story.characters.length}
            </span>
          }
        />
        <Meta
          label="Chương"
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
          Danh sách chương
        </h3>
        {story.chapters.length === 0 ? (
          <p className="text-xs text-muted-foreground">Chưa có chương nào.</p>
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
                    {STATUS_LABEL[ch.status]}
                  </Badge>
                </li>
              ))}
            </ul>
          </ScrollArea>
        )}
      </div>

      <div className="space-y-2">
        <div className="flex gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={handleExport}
            className="flex-1 gap-1.5"
          >
            <Download className="size-4" aria-hidden />
            Xuất JSON
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => setConfirmOpen(true)}
            className="text-destructive hover:bg-destructive/10"
            aria-label="Xoá truyện"
          >
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={exportingFmt !== null}
            onClick={() => void handleServerExport("docx")}
            className="gap-1.5"
            aria-label="Xuất DOCX (Word)"
          >
            {exportingFmt === "docx" ? "…" : "DOCX"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={exportingFmt !== null}
            onClick={() => void handleServerExport("pdf")}
            className="gap-1.5"
            aria-label="Xuất PDF"
          >
            {exportingFmt === "pdf" ? "…" : "PDF"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={exportingFmt !== null}
            onClick={() => void handleServerExport("epub")}
            className="gap-1.5"
            aria-label="Xuất EPUB (ebook)"
          >
            {exportingFmt === "epub" ? "…" : "EPUB"}
          </Button>
        </div>
      </div>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Xoá truyện?</DialogTitle>
            <DialogDescription>
              Hành động này không thể hoàn tác. Hãy xuất JSON nếu bạn muốn giữ lại bản
              sao.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              Huỷ
            </DialogClose>
            <Button
              type="button"
              variant="destructive"
              onClick={() => {
                onDelete(story.id);
                setConfirmOpen(false);
                toast.success("Đã xoá truyện");
              }}
            >
              Xoá
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
