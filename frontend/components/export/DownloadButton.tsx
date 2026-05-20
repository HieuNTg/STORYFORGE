"use client";

import * as React from "react";
import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";

export interface DownloadButtonProps {
  /**
   * Direct download URL. When present the component renders as an
   * anchor with the native `download` attribute — no JS fetch — which
   * works under a static export.
   */
  href?: string;
  filename?: string;
  onClick?: () => void;
  isLoading?: boolean;
  label?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * Native browser download trigger. Renders an anchor when `href` is provided
 * so the browser handles the download flow without a JS fetch; falls back to
 * a button when only `onClick` is given.
 */
export function DownloadButton({
  href,
  filename,
  onClick,
  isLoading = false,
  label,
  className,
  disabled = false,
}: DownloadButtonProps) {
  const text = isLoading ? "Đang tải xuống..." : label ?? "Tải xuống";
  const classes = cn(buttonVariants({ variant: "default" }), className);

  if (href && !disabled && !isLoading) {
    return (
      <a
        href={href}
        download={filename ?? true}
        onClick={onClick}
        className={classes}
        data-slot="button"
      >
        <Download aria-hidden />
        {text}
      </a>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isLoading}
      className={classes}
      data-slot="button"
      aria-busy={isLoading || undefined}
    >
      <Download aria-hidden />
      {text}
    </button>
  );
}
