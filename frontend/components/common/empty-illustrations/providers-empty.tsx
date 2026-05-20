import { Plug } from "lucide-react";

/**
 * Empty illustration — Providers (no provider configured).
 * Plug icon with a small "outlet" dot suggesting a connection point.
 */
export default function ProvidersEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có nhà cung cấp nào được kết nối"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <Plug
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      {/* Decorative "outlet" dots on the right */}
      <span
        aria-hidden
        className="absolute top-1/2 right-3 size-1.5 -translate-y-1/2 rounded-full bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute top-[40%] right-3 size-1 -translate-y-1/2 rounded-full bg-muted-foreground/40"
      />
    </div>
  );
}
