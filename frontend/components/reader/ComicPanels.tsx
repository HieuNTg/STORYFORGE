"use client";

import * as React from "react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export interface ComicPanelsProps {
  /**
   * Chapter image URLs (already /media-prefixed). When the backend
   * `comic_compositor_enabled` flag is on, each entry is a fully composed
   * comic PAGE (panels + gutters + Vietnamese speech bubbles, ~1600×2263 ISO
   * portrait); when off, each entry is a single loose illustration panel.
   * Both modes render identically here: scale to container width, height
   * follows the image (`object-contain`, no fixed-aspect crop), so a tall
   * page is shown in full and stays legible at phone width.
   */
  images: string[];
  /** Alt text prefix — e.g. "Minh hoạ chương 3". Image index is appended. */
  alt: string;
  /** Whether regeneration is currently in flight. */
  loading?: boolean;
  /** Click handler for the regenerate button. Hidden when undefined. */
  onRegenerate?: () => void;
  /**
   * Header label semantics. "page" labels entries as composed comic pages
   * (compositor on); "panel" (default) labels them as loose illustration
   * panels (compositor off / legacy). Purely cosmetic — layout is identical.
   */
  unit?: "panel" | "page";
  className?: string;
}

/**
 * ComicPanels — vertical comic strip (truyện tranh) for a chapter.
 *
 * Renders every generated image stacked top-to-bottom (webtoon style),
 * whether each entry is a loose illustration panel or a fully composed comic
 * page. Every image scales to the container width with its height following
 * the source aspect (`object-contain`), so tall ISO comic pages are never
 * cropped to 9:16 or stretched — letters stay readable at phone width. Each
 * image tracks its own load failure so one broken URL doesn't blank the strip.
 * A single regenerate button sits in the top-right of the strip header.
 */
export function ComicPanels({
  images,
  alt,
  loading,
  onRegenerate,
  unit = "panel",
  className,
}: ComicPanelsProps) {
  const t = useTranslations("reader");
  const [failed, setFailed] = React.useState<Record<number, boolean>>({});

  const markFailed = React.useCallback((i: number) => {
    setFailed((prev) => (prev[i] ? prev : { ...prev, [i]: true }));
  }, []);

  return (
    <section
      className={cn(
        "relative w-full overflow-hidden rounded-xl border bg-muted/40",
        "border-[color:var(--reader-rule,var(--border))]",
        className,
      )}
      aria-label={alt}
    >
      {onRegenerate ? (
        <div className="flex items-center justify-between gap-2 px-3 py-2">
          <span className="text-xs text-muted-foreground">
            {unit === "page"
              ? t("illustration_pages", { count: images.length })
              : t("illustration_panels", { count: images.length })}
          </span>
          <Button
            type="button"
            size="icon"
            variant="outline"
            disabled={loading}
            onClick={onRegenerate}
            aria-label={t("illustration_regenerate")}
            title={t("illustration_regenerate")}
            className="size-8 bg-background/70 backdrop-blur"
          >
            <RefreshCw
              className={cn("size-4", loading && "animate-spin")}
              aria-hidden
            />
          </Button>
        </div>
      ) : null}

      <div className="flex flex-col gap-1">
        {images.map((src, i) =>
          failed[i] ? (
            <div
              key={`${src}-${i}`}
              className={cn(
                "flex w-full items-center justify-center text-xs text-muted-foreground",
                // Reserve a plausible aspect while the (failed) image would
                // have loaded. Composed comic pages are tall ISO portrait
                // (~1:1.414); loose panels are nearer 3:4.
                unit === "page" ? "aspect-[1131/1600]" : "aspect-[3/4]",
              )}
            >
              {t("illustration_empty")}
            </div>
          ) : (
            <div key={`${src}-${i}`} className="relative flex w-full justify-center">
              {/*
                Comic images are portrait (loose panels ~3:4; composed comic
                pages ~1:1.414 ISO). Let height follow the source aspect:
                `h-auto w-full object-contain` scales to container width with
                no fixed-aspect crop, so tall pages display in full and stay
                legible at phone width. `unoptimized` is required — the app
                runs `next/image` with `images.unoptimized` (next.config.ts).
                The intrinsic width/height below are only an aspect HINT for
                next/image's pre-load reservation; `h-auto` lets the real
                source ratio win once loaded.
              */}
              <Image
                src={src}
                alt={`${alt} — ${i + 1}`}
                width={1131}
                height={1600}
                sizes="(max-width: 768px) 100vw, 720px"
                className="h-auto w-full object-contain"
                onError={() => markFailed(i)}
                unoptimized
              />
            </div>
          ),
        )}
      </div>
    </section>
  );
}
