"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function ShellError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Phase 1+: wire to telemetry. For Phase 0, surface to console.
    console.error("[shell:error]", error);
  }, [error]);

  return (
    <div className="flex max-w-xl flex-col gap-3">
      <h2 className="text-xl font-semibold tracking-tight">Đã xảy ra lỗi</h2>
      <p className="text-sm text-muted-foreground">
        {error.message || "Unknown error"}
        {error.digest ? <span className="ml-2 font-mono text-xs">({error.digest})</span> : null}
      </p>
      <div>
        <Button type="button" variant="outline" size="sm" onClick={reset}>
          Thử lại
        </Button>
      </div>
    </div>
  );
}
