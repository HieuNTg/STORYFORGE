"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export type ReaderTheme = "midnight" | "sepia" | "dark" | "light";
export type ReaderColumnWidth = "narrow" | "medium" | "wide";

export interface ReaderShellProps {
  chapterList: React.ReactNode;
  prose: React.ReactNode;
  controls: React.ReactNode;
  columnWidth: ReaderColumnWidth;
  theme: ReaderTheme;
  className?: string;
}

const COLUMN_MAX: Record<ReaderColumnWidth, string> = {
  narrow: "max-w-[36rem]",
  medium: "max-w-[44rem]",
  wide: "max-w-[56rem]",
};

/**
 * ReaderShell — three-column layout for the Reader page.
 *
 * - Left: chapter list (~260px), collapses below lg.
 * - Center: prose pane, max-width clamped by `columnWidth`.
 * - Right (or top sticky bar): reader controls.
 *
 * The prose pane is wrapped in `reader-theme-{midnight|sepia|dark|light}` so the
 * scoped reader tokens (defined in globals.css) apply ONLY to the prose,
 * not the rest of the app.
 */
export function ReaderShell({
  chapterList,
  prose,
  controls,
  columnWidth,
  theme,
  className,
}: ReaderShellProps) {
  return (
    <div className={cn("flex w-full flex-col gap-4 lg:flex-row lg:gap-6", className)}>
      <aside
        aria-label="Danh sách chương"
        className="w-full shrink-0 lg:w-[260px]"
      >
        {chapterList}
      </aside>

      <main className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-center justify-end">{controls}</div>

        <div
          className={cn(
            "reader-theme",
            `reader-theme-${theme}`,
            "mx-auto w-full rounded-xl border px-5 py-8 sm:px-8 sm:py-10",
            COLUMN_MAX[columnWidth]
          )}
          style={{
            backgroundColor: "var(--reader-bg)",
            color: "var(--reader-fg)",
            borderColor: "var(--reader-rule)",
          }}
        >
          {prose}
        </div>
      </main>
    </div>
  );
}
