"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { fontSerif } from "@/app/fonts";

export type ReaderFontFamily = "sans" | "serif";

export interface ChapterReaderProps {
  /** Raw chapter content. Paragraphs separated by blank lines (\n\n). */
  content: string;
  /** Optional chapter title rendered as h1 above the prose. */
  title?: string;
  fontFamily: ReaderFontFamily;
  /** Pixel font size (e.g. 16, 18). */
  fontSize: number;
  /** Unitless line-height multiplier (e.g. 1.6). */
  lineHeight: number;
  className?: string;
}

/**
 * Splits the raw chapter string into paragraphs.
 * Supports blank-line separators (\n\n+) and falls back to single-newline.
 */
function paragraphsFrom(raw: string): string[] {
  const normalized = raw.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];
  // Prefer blank-line splits; fall back to single newlines if none found.
  const blocks = normalized.split(/\n{2,}/);
  return blocks.length > 1 ? blocks : normalized.split(/\n+/);
}

/**
 * ChapterReader — the prose surface.
 * Vietnamese novel style: first-line indent on body paragraphs, no indent
 * directly after a heading. Uses scoped --reader-* tokens (set by the
 * ReaderShell wrapper) for color, so day/sepia/night themes work without
 * touching the rest of the app.
 *
 * Serif opt-in: when fontFamily === "serif", we attach the
 * `fontSerif.variable` (Source Serif 4) and switch to font-serif. The font is
 * lazy-loaded via next/font (preload: false in app/fonts.ts) so users who
 * never enable serif never pay the network cost.
 */
export function ChapterReader({
  content,
  title,
  fontFamily,
  fontSize,
  lineHeight,
  className,
}: ChapterReaderProps) {
  const paragraphs = React.useMemo(() => paragraphsFrom(content), [content]);

  return (
    <article
      data-font-family={fontFamily}
      className={cn(
        "reader-prose flex flex-col gap-4",
        fontFamily === "serif" ? `${fontSerif.variable} font-serif` : "font-sans",
        className
      )}
      style={{
        fontSize: `${fontSize}px`,
        lineHeight: lineHeight,
        color: "var(--reader-fg)",
      }}
    >
      {title ? (
        <header
          className="flex flex-col gap-1 border-b pb-4"
          style={{ borderColor: "var(--reader-rule)" }}
        >
          <h1
            className="font-semibold leading-tight"
            style={{
              color: "var(--reader-fg)",
              fontSize: `${Math.round(fontSize * 1.55)}px`,
              lineHeight: 1.2,
            }}
          >
            {title}
          </h1>
        </header>
      ) : null}

      {paragraphs.length === 0 ? (
        <p style={{ color: "var(--reader-muted)" }}>Chưa có nội dung.</p>
      ) : (
        paragraphs.map((para, idx) => (
          <p
            key={idx}
            className={cn(
              // Vietnamese novel convention: first-line indent on body paragraphs.
              // First paragraph after a heading does NOT indent.
              idx === 0 && title ? "" : "indent-[1.5em]"
            )}
            style={{
              // Trim margins; gap-4 on parent provides vertical rhythm.
              margin: 0,
            }}
          >
            {para}
          </p>
        ))
      )}
    </article>
  );
}
