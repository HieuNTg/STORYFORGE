import { Download, FileText } from "lucide-react";

/**
 * Empty illustration — Export (no export jobs yet).
 * Document with a download arrow.
 */
export default function ExportEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có file xuất nào"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <FileText
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      <span
        aria-hidden
        className="absolute right-3 bottom-3 flex size-6 items-center justify-center rounded-full bg-background ring-1 ring-border"
      >
        <Download className="size-3.5 text-muted-foreground" strokeWidth={1.75} />
      </span>
    </div>
  );
}
