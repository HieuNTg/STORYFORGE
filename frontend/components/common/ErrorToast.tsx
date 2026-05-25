"use client";

import { toast } from "sonner";

/**
 * ErrorToast — thin sonner wrapper with VN copy templates for the
 * common failure modes surfaced by TanStack Query + fetch.
 *
 * Standardizes message shape so callers don't reinvent error strings
 * (and don't leak provider stack traces — see Phase 5 security note).
 */

export type ErrorKind = "network" | "server" | "validation" | "unknown";

const TITLES_VI: Record<ErrorKind, string> = {
  network: "Mất kết nối",
  server: "Máy chủ gặp lỗi",
  validation: "Dữ liệu chưa hợp lệ",
  unknown: "Đã xảy ra lỗi",
};

const DESCRIPTIONS_VI: Record<ErrorKind, string> = {
  network: "Kiểm tra mạng rồi thử lại.",
  server: "Vui lòng thử lại sau ít phút.",
  validation: "Hãy xem lại các trường và thử lại.",
  unknown: "Vui lòng thử lại.",
};

const TITLES_EN: Record<ErrorKind, string> = {
  network: "Connection Lost",
  server: "Server Error",
  validation: "Invalid Data",
  unknown: "An error occurred",
};

const DESCRIPTIONS_EN: Record<ErrorKind, string> = {
  network: "Please check your network and try again.",
  server: "Please try again in a few minutes.",
  validation: "Please review the fields and try again.",
  unknown: "Please try again.",
};

export interface ErrorToastOptions {
  description?: string;
  action?: { label: string; onClick: () => void };
}

function classify(err: unknown): ErrorKind {
  if (typeof err === "object" && err !== null) {
    const e = err as { name?: string; status?: number; message?: string };
    if (e.name === "TypeError" || /network|fetch/i.test(e.message ?? "")) return "network";
    if (typeof e.status === "number") {
      if (e.status >= 500) return "server";
      if (e.status === 422 || e.status === 400) return "validation";
    }
  }
  return "unknown";
}

export function showErrorToast(err: unknown, opts: ErrorToastOptions = {}) {
  const kind = classify(err);
  const locale = typeof window !== "undefined" ? document.documentElement.lang : "vi";
  const titles = locale === "en" ? TITLES_EN : TITLES_VI;
  const descriptions = locale === "en" ? DESCRIPTIONS_EN : DESCRIPTIONS_VI;

  const description =
    opts.description ??
    (err instanceof Error ? err.message : undefined) ??
    descriptions[kind];
  return toast.error(titles[kind], {
    description,
    action: opts.action,
  });
}

export function showErrorToastKind(
  kind: ErrorKind,
  opts: ErrorToastOptions = {},
) {
  const locale = typeof window !== "undefined" ? document.documentElement.lang : "vi";
  const titles = locale === "en" ? TITLES_EN : TITLES_VI;
  const descriptions = locale === "en" ? DESCRIPTIONS_EN : DESCRIPTIONS_VI;

  return toast.error(titles[kind], {
    description: opts.description ?? descriptions[kind],
    action: opts.action,
  });
}
