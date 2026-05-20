"use client";

/**
 * ExportClient — client-side body of `/export?id=…`.
 *
 * Owns the 4 format cards, the config sheet, and the download trigger. The
 * parent page reads `id` from the search params and passes it in here.
 *
 * Backend reality: only PDF + EPUB have dedicated endpoints today
 * (`api/export_routes.py`). HTML/Markdown surface as "sắp ra mắt" and are
 * gated by `SUPPORTED` below.
 */

import * as React from "react";
import { FileText, FileType2, Globe, BookOpen } from "lucide-react";
import { toast } from "sonner";

import { FormatCards, type ExportFormatOption } from "@/components/export/FormatCards";
import {
  ExportConfigSheet,
  type ExportFormat,
} from "@/components/export/ExportConfigSheet";

const FORMATS: ExportFormatOption[] = [
  {
    id: "epub",
    label: "EPUB",
    description: "Định dạng ebook chuẩn, tương thích Kindle.",
    icon: BookOpen,
    recommended: true,
  },
  {
    id: "pdf",
    label: "PDF",
    description: "In ấn, lưu trữ — bố cục cố định.",
    icon: FileType2,
  },
  {
    id: "html",
    label: "HTML",
    description: "Trang web tĩnh — sắp ra mắt.",
    icon: Globe,
  },
  {
    id: "markdown",
    label: "Markdown",
    description: "Văn bản thuần — sắp ra mắt.",
    icon: FileText,
  },
];

// Backend only ships PDF + EPUB endpoints today. HTML/Markdown surface as
// "coming soon" so the design doesn't lie about what's available.
// TODO: backend has no HTML/Markdown export endpoint — see
// plans/260519-1908-ui-rebuild-react-shadcn/phase-03-settings-providers-export.md
const SUPPORTED: ReadonlySet<ExportFormat> = new Set(["pdf", "epub"]);

async function triggerDownload(format: ExportFormat, id: string) {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
  const url = `${base.replace(/\/+$/, "")}/api/export/${format}/${encodeURIComponent(id)}`;
  const csrf =
    typeof document !== "undefined"
      ? (document.cookie.match(/(?:^|; )csrf_token=([^;]*)/)?.[1] ?? null)
      : null;
  const res = await fetch(url, {
    method: "POST",
    credentials: "include",
    headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body?.error?.message ?? body?.detail ?? msg;
    } catch {
      /* swallow */
    }
    throw new Error(msg || "Tải xuống thất bại");
  }
  const blob = await res.blob();
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = objectUrl;
  a.download = `${id}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000);
}

export interface ExportClientProps {
  id: string;
}

export function ExportClient({ id }: ExportClientProps) {
  const [selected, setSelected] = React.useState<ExportFormat | null>(null);
  const [sheetOpen, setSheetOpen] = React.useState(false);
  const [downloading, setDownloading] = React.useState(false);

  const onSelect = (formatId: string) => {
    setSelected(formatId as ExportFormat);
    setSheetOpen(true);
  };

  const onDownload = async () => {
    if (!selected) return;
    if (!SUPPORTED.has(selected)) {
      toast.error("Định dạng này sắp ra mắt");
      return;
    }
    setDownloading(true);
    try {
      await triggerDownload(selected, id);
      toast.success(`Đã tạo ${selected.toUpperCase()}`);
      setSheetOpen(false);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Tải xuống thất bại";
      toast.error(msg);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <>
      <FormatCards
        formats={FORMATS}
        selected={selected ?? undefined}
        onSelect={onSelect}
      />
      <ExportConfigSheet
        open={sheetOpen}
        onOpenChange={setSheetOpen}
        format={selected}
        onDownload={onDownload}
        isDownloading={downloading}
        filename={selected ? `${id}.${selected}` : undefined}
        config={
          <div className="flex flex-col gap-3 py-2 text-sm text-muted-foreground">
            {selected && SUPPORTED.has(selected) ? (
              <>
                <p>
                  Sẵn sàng xuất bản dưới dạng{" "}
                  <strong className="text-foreground">{selected.toUpperCase()}</strong>.
                </p>
                <p>Truyện sẽ được biên dịch từ phiên bản đã lưu hiện tại.</p>
              </>
            ) : (
              <p>Định dạng {selected?.toUpperCase()} sắp ra mắt.</p>
            )}
          </div>
        }
      />
    </>
  );
}
