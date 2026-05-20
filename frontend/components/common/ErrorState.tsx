"use client";

import * as React from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * ErrorState — destructive-tinted sibling of EmptyState.
 * Used by error boundaries (`error.tsx`) and inline query failures.
 * Generous line-height for Vietnamese diacritic stacking.
 */
export interface ErrorStateProps {
  title?: string;
  description?: string;
  onRetry?: () => void;
  /** Optional illustration override; falls back to a destructive icon badge. */
  illustration?: React.ReactNode;
  className?: string;
}

export function ErrorState({
  title = "Đã xảy ra lỗi",
  description,
  onRetry,
  illustration,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-4 px-6 py-12 text-center leading-relaxed",
        className
      )}
    >
      {illustration ? (
        <div className="mb-1">{illustration}</div>
      ) : (
        <div
          aria-hidden
          className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive"
        >
          <AlertTriangle className="size-6" strokeWidth={1.5} />
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <h3 className="text-[18px] font-medium leading-snug text-foreground">
          {title}
        </h3>
        {description ? (
          <p className="mx-auto max-w-prose text-sm leading-relaxed text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>

      {onRetry ? (
        <Button variant="outline" onClick={onRetry} className="mt-1">
          <RefreshCw className="size-4" strokeWidth={1.75} aria-hidden />
          Thử lại
        </Button>
      ) : null}
    </div>
  );
}
