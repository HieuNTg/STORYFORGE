import { Activity } from "lucide-react";

/**
 * Empty illustration — Usage (no API calls yet).
 * Pulse/activity line with decorative "tick" marks.
 */
export default function UsageEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có dữ liệu sử dụng"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <Activity
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      {/* Decorative axis ticks */}
      <span
        aria-hidden
        className="absolute right-4 bottom-3 left-4 h-px bg-muted-foreground/30"
      />
      <span
        aria-hidden
        className="absolute bottom-2 left-4 h-1 w-px bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute bottom-2 left-1/2 h-1 w-px -translate-x-1/2 bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute right-4 bottom-2 h-1 w-px bg-muted-foreground/40"
      />
    </div>
  );
}
