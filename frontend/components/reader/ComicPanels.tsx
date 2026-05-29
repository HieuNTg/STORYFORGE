"use client";

import * as React from "react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export interface ComicPanelsProps {
  /** Panel image URLs (already /media-prefixed). */
  images: string[];
  /** Alt text prefix — e.g. "Minh hoạ chương 3". Panel index is appended. */
  alt: string;
  /** Whether regeneration is currently in flight. */
  loading?: boolean;
  /** Click handler for the regenerate button. Hidden when undefined. */
  onRegenerate?: () => void;
  className?: string;
}

/**
 * ComicPanels — vertical comic strip (truyện tranh) for a chapter.
 *
 * Renders every generated panel stacked top-to-bottom (webtoon style). Each
 * panel tracks its own load failure so one broken URL doesn't blank the strip.
 * A single regenerate button sits in the top-right of the strip header.
 */
export function ComicPanels({
  images,
  alt,
  loading,
  onRegenerate,
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
            {t("illustration_panels", { count: images.length })}
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
              className="flex aspect-[3/4] w-full items-center justify-center text-xs text-muted-foreground"
            >
              {t("illustration_empty")}
            </div>
          ) : (
            <div key={`${src}-${i}`} className="relative w-full">
              {/* Comic panels are portrait-ish; let height follow the image. */}
              <Image
                src={src}
                alt={`${alt} — ${i + 1}`}
                width={1024}
                height={1024}
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
