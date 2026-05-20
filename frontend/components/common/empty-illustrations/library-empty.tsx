import { LibraryBig, Plus } from "lucide-react";

/**
 * Empty illustration — Library page (no stories yet).
 * Books with a tiny "add" affordance below.
 */
export default function LibraryEmpty() {
  return (
    <div
      role="img"
      aria-label="Thư viện trống"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      {/* Decorative dots */}
      <span
        aria-hidden
        className="absolute top-3 right-3 size-1 rounded-full bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute bottom-4 left-4 size-1 rounded-full bg-muted-foreground/40"
      />
      <LibraryBig
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      <span
        aria-hidden
        className="absolute right-2 bottom-2 flex size-5 items-center justify-center rounded-full bg-background ring-1 ring-border"
      >
        <Plus className="size-3 text-muted-foreground" strokeWidth={2} />
      </span>
    </div>
  );
}
