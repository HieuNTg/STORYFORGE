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

const TITLES: Record<ErrorKind, string> = {
  network: "Mất kết nối",
  server: "Máy chủ gặp lỗi",
  validation: "Dữ liệu chưa hợp lệ",
  unknown: "Đã xảy ra lỗi",
};

const DESCRIPTIONS: Record<ErrorKind, string> = {
  network: "Kiểm tra mạng rồi thử lại.",
  server: "Vui lòng thử lại sau ít phút.",
  validation: "Hãy xem lại các trường và thử lại.",
  unknown: "Vui lòng thử lại.",
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
  const description =
    opts.description ??
    (err instanceof Error ? err.message : undefined) ??
    DESCRIPTIONS[kind];
  return toast.error(TITLES[kind], {
    description,
    action: opts.action,
  });
}

export function showErrorToastKind(
  kind: ErrorKind,
  opts: ErrorToastOptions = {},
) {
  return toast.error(TITLES[kind], {
    description: opts.description ?? DESCRIPTIONS[kind],
    action: opts.action,
  });
}
