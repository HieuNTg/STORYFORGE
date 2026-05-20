import { ImageIcon } from "lucide-react";

/**
 * Empty illustration — Gallery (no images/covers yet).
 * Image frame with decorative 2-cell mini-grid suggesting "more coming".
 */
export default function GalleryEmpty() {
  return (
    <div
      role="img"
      aria-label="Bộ sưu tập trống"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <ImageIcon
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      {/* Decorative mini grid showing potential gallery cells */}
      <span
        aria-hidden
        className="absolute top-3 right-3 size-2 rounded-sm bg-muted-foreground/30"
      />
      <span
        aria-hidden
        className="absolute right-3 bottom-3 size-2 rounded-sm bg-muted-foreground/20"
      />
    </div>
  );
}
