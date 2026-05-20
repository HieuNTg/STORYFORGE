import { Workflow, Sparkles } from "lucide-react";

/**
 * Empty illustration — Pipeline page.
 * A workflow node with a small sparkle to suggest "ready to generate".
 */
export default function PipelineEmpty() {
  return (
    <div
      role="img"
      aria-label="Chưa có pipeline nào đang chạy"
      className="relative flex h-28 w-28 items-center justify-center"
    >
      {/* Soft backdrop */}
      <div
        aria-hidden
        className="absolute inset-0 rounded-2xl bg-muted/40"
      />
      {/* Decorative dots */}
      <span
        aria-hidden
        className="absolute top-2 left-3 size-1 rounded-full bg-muted-foreground/40"
      />
      <span
        aria-hidden
        className="absolute right-3 bottom-3 size-1 rounded-full bg-muted-foreground/40"
      />
      {/* Focal icon */}
      <Workflow
        aria-hidden
        className="relative size-10 text-muted-foreground"
        strokeWidth={1.5}
      />
      {/* Accent sparkle */}
      <Sparkles
        aria-hidden
        className="absolute top-2 right-2 size-4 text-accent/60"
        strokeWidth={1.5}
      />
    </div>
  );
}
