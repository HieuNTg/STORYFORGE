"use client";

import * as React from "react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export interface IllustrationBannerProps {
  /** Image src — provider-resolved URL or placeholder. */
  src?: string | null;
  /** Alt text — usually "Minh hoạ chương N: title". */
  alt: string;
  /** Whether regeneration is currently in flight. */
  loading?: boolean;
  /** Click handler for the regenerate icon button. Hidden when undefined. */
  onRegenerate?: () => void;
  /** Optional caption rendered below the image (e.g., character names). */
  caption?: string;
  className?: string;
}

/**
 * IllustrationBanner — cinematic header image for a chapter.
 *
 * Aspect ratio 21:9, dark vignette overlay, optional regenerate fab in the
 * top-right corner. Skeleton shimmer when src is missing AND not yet failed.
 */
export function IllustrationBanner({
  src,
  alt,
  loading,
  onRegenerate,
  caption,
  className,
}: IllustrationBannerProps) {
  const t = useTranslations("reader");
  const [failed, setFailed] = React.useState(false);
  const hasImage = !!src && !failed;

  return (
    <figure
      className={cn(
        "relative w-full overflow-hidden rounded-xl border bg-muted/40",
        "border-[color:var(--reader-rule,var(--border))]",
        className,
      )}
    >
      <div className="relative aspect-[21/9] w-full">
        {hasImage ? (
          <Image
            src={src as string}
            alt={alt}
            fill
            sizes="(max-width: 768px) 100vw, 720px"
            className="object-cover"
            onError={() => setFailed(true)}
            unoptimized
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-xs text-muted-foreground">
            {loading ? t("illustration_loading") : t("illustration_empty")}
          </div>
        )}
        {/* Vignette */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/40 via-transparent to-transparent"
        />
        {onRegenerate ? (
          <Button
            type="button"
            size="icon"
            variant="outline"
            disabled={loading}
            onClick={onRegenerate}
            aria-label={t("illustration_regenerate")}
            title={t("illustration_regenerate")}
            className="absolute right-3 top-3 size-8 bg-background/70 backdrop-blur"
          >
            <RefreshCw
              className={cn("size-4", loading && "animate-spin")}
              aria-hidden
            />
          </Button>
        ) : null}
      </div>
      {caption ? (
        <figcaption className="px-4 py-2 font-serif text-xs italic text-muted-foreground">
          {caption}
        </figcaption>
      ) : null}
    </figure>
  );
}
