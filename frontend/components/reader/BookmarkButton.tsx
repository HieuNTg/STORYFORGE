"use client";

import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Bookmark, BookmarkCheck } from "lucide-react";

export interface BookmarkButtonProps {
  isBookmarked: boolean;
  onToggle: () => void;
  loading?: boolean;
  className?: string;
}

export function BookmarkButton({
  isBookmarked,
  onToggle,
  loading = false,
  className,
}: BookmarkButtonProps) {
  const t = useTranslations("reader");
  const label = isBookmarked ? t("bookmark_check") : t("bookmark");

  return (
    <Button
      type="button"
      variant={isBookmarked ? "secondary" : "outline"}
      size="sm"
      onClick={onToggle}
      disabled={loading}
      aria-pressed={isBookmarked}
      aria-label={label}
      title={label}
      className={cn(className)}
    >
      {isBookmarked ? (
        <BookmarkCheck aria-hidden className={loading ? "opacity-50" : undefined} />
      ) : (
        <Bookmark aria-hidden className={loading ? "opacity-50" : undefined} />
      )}
      <span className="hidden sm:inline">{label}</span>
    </Button>
  );
}
