import { BookOpen } from "lucide-react";

/**
 * Empty illustration — Reader with no chapters yet.
 * Open book with decorative "page lines".
 */
export default function LibraryReaderEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có chương nào để đọc"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <BookOpen
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      {/* Decorative "page lines" */}
      <span
        aria-hidden
        className="absolute right-4 bottom-5 h-px w-6 bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute right-4 bottom-3.5 h-px w-4 bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute bottom-5 left-4 h-px w-6 bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute bottom-3.5 left-4 h-px w-4 bg-muted-foreground/40"
      />
    </div>
  );
}
