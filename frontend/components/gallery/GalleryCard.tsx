"use client";

/**
 * GalleryCard — final visual treatment (Phase 4 UI design).
 *
 * Visual contract (per Phase 4 brief):
 *   - aspect-video (16:9) cover container, group hover scales cover 1.02
 *   - genre badge anchored top-left over the cover
 *   - length pill anchored bottom-right over the cover
 *   - title `line-clamp-2`, leading-snug
 *   - author/stats row below title (currently: created-at date)
 *   - hover: 200ms ease-out subtle lift + soft shadow (one-shot, no infinite)
 *   - light + dark parity via tokens only
 *   - focus-visible ring on the interactive wrapper
 *
 * API contract preserved from Frontend Developer stub:
 *   - props: { item, onOpen, className, previewBlur }
 *   - item shape from @/lib/api/gallery (share_id, story_title, ...)
 */

import * as React from "react";
import { ImageIcon } from "lucide-react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { GalleryItem } from "@/lib/api/gallery";

export interface GalleryCardProps {
  item: GalleryItem;
  /** Optional pre-computed low-res blurred preview (base64 / data URL). */
  previewBlur?: string;
  onOpen?: (item: GalleryItem) => void;
  className?: string;
}

const LENGTH_LABEL: Record<NonNullable<GalleryItem["length"]>, string> = {
  short: "Ngắn",
  medium: "Vừa",
  long: "Dài",
};

const DATE_FORMATTER = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});

function formatDate(iso?: string): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  return DATE_FORMATTER.format(new Date(t));
}

export function GalleryCard({
  item,
  previewBlur,
  onOpen,
  className,
}: GalleryCardProps) {
  const interactive = typeof onOpen === "function";
  const title = item.story_title || item.share_id;
  const created = formatDate(item.created_at);

  const card = (
    <Card
      size="sm"
      className={cn(
        // Card primitive already wraps with `flex flex-col gap-3 py-3` (size=sm).
        // We zero the top padding so the cover sits flush at the rounded top
        // edge, while body padding remains for the title + meta row.
        "flex h-full flex-col gap-0 py-0",
        "motion-lift hover:shadow-md",
        className,
      )}
    >
      {/* 16:9 cover with overlay badges + hover scale on the image only.
       * `rounded-t-xl` keeps the corner radius continuous with the Card. */}
      <div className="relative aspect-video w-full overflow-hidden rounded-t-xl bg-muted">
        {previewBlur ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewBlur}
            alt=""
            aria-hidden
            className="absolute inset-0 h-full w-full scale-110 object-cover blur-md"
          />
        ) : null}
        {item.cover_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={item.cover_url}
            alt=""
            loading="lazy"
            decoding="async"
            className={cn(
              "relative h-full w-full object-cover",
              "transition-transform duration-[var(--motion-base)] ease-[var(--ease-out)]",
              "group-hover/card:scale-[1.02]",
            )}
          />
        ) : (
          <div
            aria-hidden
            className="relative flex h-full w-full items-center justify-center text-muted-foreground"
          >
            <ImageIcon className="size-8" strokeWidth={1.5} />
          </div>
        )}

        {/* Genre badge — top-left over cover. */}
        {item.genre ? (
          <Badge
            variant="secondary"
            className={cn(
              "absolute top-2 left-2 max-w-[60%] truncate",
              "border border-border/40 bg-background/85 text-foreground backdrop-blur-sm",
              "shadow-sm",
            )}
          >
            {item.genre}
          </Badge>
        ) : null}

        {/* Length pill — bottom-right over cover. */}
        {item.length ? (
          <span
            className={cn(
              "absolute right-2 bottom-2 inline-flex items-center rounded-full px-2 py-0.5",
              "border border-border/40 bg-background/85 text-[11px] font-medium text-foreground",
              "backdrop-blur-sm shadow-sm tabular-nums",
            )}
          >
            {LENGTH_LABEL[item.length]}
          </span>
        ) : null}
      </div>

      <CardHeader className="px-4 pt-4 pb-1">
        <CardTitle className="line-clamp-2 text-[15px] leading-snug">
          {title}
        </CardTitle>
      </CardHeader>

      <CardContent
        className={cn(
          "mt-auto flex items-center justify-between gap-2 px-4 pt-1 pb-4",
          "text-xs text-muted-foreground",
        )}
      >
        <span className="truncate" aria-label="ID chia sẻ">
          {item.share_id.slice(0, 8)}…
        </span>
        {created ? <span className="tabular-nums">{created}</span> : null}
      </CardContent>
    </Card>
  );

  if (!interactive) return card;

  return (
    <button
      type="button"
      onClick={() => onOpen?.(item)}
      aria-label={title}
      className={cn(
        "block w-full text-left",
        "rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
      )}
    >
      {card}
    </button>
  );
}
