"use client";

import * as React from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { DownloadButton } from "./DownloadButton";

export type ExportFormat = "epub" | "pdf" | "html" | "markdown";

export interface ExportConfigSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  format: ExportFormat | null;
  /** Format-specific configuration body, provided by the caller. */
  config: ReactNode;
  onDownload: () => void;
  isDownloading?: boolean;
  /** When provided, the download triggers a native anchor click. */
  downloadHref?: string;
  filename?: string;
  className?: string;
}

const formatLabel: Record<ExportFormat, string> = {
  epub: "EPUB",
  pdf: "PDF",
  html: "HTML",
  markdown: "Markdown",
};

export function ExportConfigSheet({
  open,
  onOpenChange,
  format,
  config,
  onDownload,
  isDownloading = false,
  downloadHref,
  filename,
  className,
}: ExportConfigSheetProps) {
  const title = format ? `Xuất bản: ${formatLabel[format]}` : "Xuất bản";

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        side="right"
        className={cn("flex w-full flex-col gap-0 sm:max-w-md", className)}
      >
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            Tùy chỉnh tuỳ chọn xuất bản trước khi tải xuống.
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-4 py-2">{config}</div>

        <SheetFooter>
          <DownloadButton
            href={downloadHref}
            filename={filename}
            onClick={onDownload}
            isLoading={isDownloading}
            disabled={!format}
          />
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
