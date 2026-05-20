import { SlidersHorizontal } from "lucide-react";

/**
 * Empty illustration — Settings (no overrides / defaults).
 * Sliders with two decorative "track" dots.
 */
export default function SettingsEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có cài đặt tuỳ chỉnh"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <SlidersHorizontal
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      <span
        aria-hidden
        className="absolute top-3 right-3 size-1 rounded-full bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute bottom-3 left-3 size-1 rounded-full bg-muted-foreground/40"
      />
    </div>
  );
}
