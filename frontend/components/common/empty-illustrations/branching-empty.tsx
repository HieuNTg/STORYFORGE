import { GitBranch } from "lucide-react";

/**
 * Empty illustration — Branching session not started.
 * Branch icon with decorative node dots.
 */
export default function BranchingEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có phiên rẽ nhánh"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      <GitBranch
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      {/* Decorative "branch endpoint" nodes */}
      <span
        aria-hidden
        className="absolute top-4 right-5 size-1.5 rounded-full bg-accent/60 ring-2 ring-background"
      />
      <span
        aria-hidden
        className="absolute right-5 bottom-5 size-1.5 rounded-full bg-muted-foreground/50 ring-2 ring-background"
      />
    </div>
  );
}
