import { UserCircle2 } from "lucide-react";

/**
 * Empty illustration — Account (no profile data).
 * Avatar silhouette with subtle ring of dots suggesting "tap to set up".
 */
export default function AccountEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có thông tin tài khoản"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <UserCircle2
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      <span
        aria-hidden
        className="absolute top-2 right-2 size-1 rounded-full bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute top-2 left-2 size-1 rounded-full bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute bottom-2 left-1/2 size-1 -translate-x-1/2 rounded-full bg-muted-foreground/40"
      />
    </div>
  );
}
