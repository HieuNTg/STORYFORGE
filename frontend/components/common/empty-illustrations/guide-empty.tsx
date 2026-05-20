import { BookMarked, HelpCircle } from "lucide-react";

/**
 * Empty illustration — Guide / FAQ (no content yet, or no search match).
 * Bookmarked book with a small help marker.
 */
export default function GuideEmpty() {
  return (
    <div
      role="img"
      aria-label="Không có nội dung hướng dẫn phù hợp"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <BookMarked
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      <span
        aria-hidden
        className="absolute right-2 bottom-2 flex size-5 items-center justify-center rounded-full bg-background ring-1 ring-border"
      >
        <HelpCircle className="size-3 text-muted-foreground" strokeWidth={1.75} />
      </span>
    </div>
  );
}
