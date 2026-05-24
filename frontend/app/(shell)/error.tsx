"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";

export default function ShellError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("shell");

  useEffect(() => {
    // Phase 1+: wire to telemetry. For Phase 0, surface to console.
    console.error("[shell:error]", error);
  }, [error]);

  return (
    <div className="flex max-w-xl flex-col gap-3">
      <h2 className="text-xl font-semibold tracking-tight">{t("error_title")}</h2>
      <p className="text-sm text-muted-foreground">
        {error.message || "Unknown error"}
        {error.digest ? <span className="ml-2 font-mono text-xs">({error.digest})</span> : null}
      </p>
      <div>
        <Button type="button" variant="outline" size="sm" onClick={reset}>
          {t("retry")}
        </Button>
      </div>
    </div>
  );
}
