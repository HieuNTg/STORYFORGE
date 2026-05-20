import { BarChart3 } from "lucide-react";

/**
 * Empty illustration — Analytics page (no data).
 * Bar chart with decorative "grid lines" underneath.
 */
export default function AnalyticsEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có dữ liệu phân tích"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      {/* Decorative horizontal grid lines */}
      <span
        aria-hidden
        className="absolute right-4 bottom-5 left-4 h-px bg-muted-foreground/30"
      />
      <span
        aria-hidden
        className="absolute right-4 bottom-8 left-4 h-px bg-muted-foreground/20"
      />
      <BarChart3
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
    </div>
  );
}
