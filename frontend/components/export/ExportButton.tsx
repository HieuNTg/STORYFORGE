"use client";

/**
 * ExportButton — single format trigger for the export page.
 *
 * Format routing (audited against `api/export_routes.py` 2026-05-20):
 *   pdf  → POST /api/export/pdf/{sid}   → file blob
 *   epub → POST /api/export/epub/{sid}  → file blob
 *   zip  → POST /api/export/zip/{sid}   → file blob (already includes HTML)
 *   html → client-side build from /api/pipeline/checkpoints/{sid} (no
 *          dedicated backend endpoint; standalone HTML is a Phase 5
 *          deliverable that does NOT require new backend work per NF2)
 *   json → client-side build from the loaded story payload
 */

import * as React from "react";
import {
  BookOpen,
  FileArchive,
  FileCode2,
  FileText,
  FileType2,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api/client";
import type { StoryDetail } from "@/lib/api/queries";

export type ExportFormat = "pdf" | "epub" | "html" | "zip" | "json";

const META: Record<
  ExportFormat,
  {
    label: string;
    description: string;
    Icon: React.ComponentType<{ className?: string }>;
  }
> = {
  pdf: {
    label: "PDF",
    description: "In ấn, lưu trữ — bố cục cố định.",
    Icon: FileType2,
  },
  epub: {
    label: "EPUB",
    description: "Ebook chuẩn, mở được trên Kindle.",
    Icon: BookOpen,
  },
  html: {
    label: "HTML",
    description: "Trang web tĩnh, kèm CSS cơ bản.",
    Icon: FileCode2,
  },
  zip: {
    label: "ZIP",
    description: "TXT + Markdown + JSON + HTML.",
    Icon: FileArchive,
  },
  json: {
    label: "JSON",
    description: "Cấu trúc thô — dùng cho tự động hoá.",
    Icon: FileText,
  },
};

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1_000);
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function storyToHtml(story: StoryDetail): string {
  const title = escapeHtml(story.title ?? "Untitled");
  const chapters = story.chapters ?? story.draft?.chapters ?? [];
  const body = chapters
    .map((c, idx) => {
      const heading = escapeHtml(c.title ?? `Chương ${c.number ?? idx + 1}`);
      const paragraphs = (c.content ?? "")
        .split(/\n{2,}/)
        .map((p) => `      <p>${escapeHtml(p)}</p>`)
        .join("\n");
      return `    <section class="chapter">\n      <h2>${heading}</h2>\n${paragraphs}\n    </section>`;
    })
    .join("\n");
  return `<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>${title}</title>
  <style>
    body { font-family: Georgia, serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; line-height: 1.7; color: #1a1a1a; }
    h1 { font-size: 2rem; text-align: center; }
    h2 { margin-top: 3rem; border-bottom: 1px solid #ccc; padding-bottom: 0.25rem; }
    p { text-indent: 1.5em; margin: 0 0 1em; }
  </style>
</head>
<body>
  <h1>${title}</h1>
${body}
</body>
</html>
`;
}

async function fetchBlob(path: string): Promise<Blob> {
  const base = process.env.NEXT_PUBLIC_API_BASE ?? "";
  const url = `${base.replace(/\/+$/, "")}${path}`;
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
  return res.blob();
}

export interface ExportButtonProps {
  format: ExportFormat;
  sid: string;
  disabled?: boolean;
  className?: string;
}

export function ExportButton({ format, sid, disabled, className }: ExportButtonProps) {
  const [loading, setLoading] = React.useState(false);
  const { label, description, Icon } = META[format];

  const handleClick = React.useCallback(async () => {
    if (!sid) return;
    setLoading(true);
    try {
      if (format === "pdf" || format === "epub" || format === "zip") {
        const blob = await fetchBlob(`/api/export/${format}/${encodeURIComponent(sid)}`);
        const ext = format === "zip" ? "zip" : format;
        downloadBlob(blob, `${sid}.${ext}`);
      } else if (format === "html") {
        const story = await apiFetch<StoryDetail>(
          `/api/pipeline/checkpoints/${encodeURIComponent(sid)}`,
        );
        const html = storyToHtml(story);
        downloadBlob(new Blob([html], { type: "text/html;charset=utf-8" }), `${sid}.html`);
      } else if (format === "json") {
        const story = await apiFetch<StoryDetail>(
          `/api/pipeline/checkpoints/${encodeURIComponent(sid)}`,
        );
        downloadBlob(
          new Blob([JSON.stringify(story, null, 2)], { type: "application/json" }),
          `${sid}.json`,
        );
      }
      toast.success(`Đã tải ${label}`);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Tải xuống thất bại";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [format, sid, label]);

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || loading || !sid}
      className={cn(
        "group flex flex-col items-start gap-2 rounded-xl border border-accent/30 bg-card/50 p-4 text-left transition-all",
        "hover:-translate-y-0.5 hover:border-accent hover:shadow-md",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0",
        className,
      )}
    >
      <div className="flex w-full items-center justify-between">
        <Icon className="size-5 text-accent" />
        {loading ? <Loader2 className="size-4 animate-spin text-accent" /> : null}
      </div>
      <div className="font-serif text-lg text-foreground">{label}</div>
      <div className="text-xs text-muted-foreground">{description}</div>
    </button>
  );
}

// Compatibility re-exports (kept while ExportClient is still referenced).
export { Button };
