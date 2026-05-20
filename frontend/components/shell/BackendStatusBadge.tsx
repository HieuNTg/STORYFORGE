"use client";

import { useEffect, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

type Status = "ok" | "down" | "unknown";

interface Props {
  collapsed?: boolean;
  /** Override health endpoint for tests. */
  endpoint?: string;
  /** Poll interval in ms. */
  intervalMs?: number;
}

/**
 * Polls `/api/health` every 30s. Renders a gold pulse dot when reachable,
 * ShieldAlert + "offline" label otherwise. AbortController used to cancel
 * in-flight requests on unmount / refresh.
 */
export function BackendStatusBadge({
  collapsed = false,
  endpoint = "/api/health",
  intervalMs = 30_000,
}: Props) {
  const [status, setStatus] = useState<Status>("unknown");
  const t = useTranslations("shell");

  useEffect(() => {
    let mounted = true;
    const controller = new AbortController();

    const check = async () => {
      try {
        const res = await fetch(endpoint, {
          signal: controller.signal,
          cache: "no-store",
        });
        if (!mounted) return;
        setStatus(res.ok ? "ok" : "down");
      } catch {
        if (mounted) setStatus("down");
      }
    };

    check();
    const id = window.setInterval(check, intervalMs);
    return () => {
      mounted = false;
      controller.abort();
      window.clearInterval(id);
    };
  }, [endpoint, intervalMs]);

  const online = status === "ok";
  const label = online ? safeT(t, "backend_online", "Backend online") : safeT(t, "backend_offline", "Backend offline");

  if (collapsed) {
    return (
      <div
        className="flex justify-center"
        title={label}
        aria-label={label}
      >
        {online ? (
          <span className="gold-pulse size-2 rounded-full bg-[var(--accent)]" />
        ) : (
          <ShieldAlert className="size-4 text-destructive" />
        )}
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 px-2 py-1 text-xs">
      {online ? (
        <span className="gold-pulse size-2 shrink-0 rounded-full bg-[var(--accent)]" />
      ) : (
        <ShieldAlert className="size-4 shrink-0 text-destructive" aria-hidden="true" />
      )}
      <span
        className={cn(
          "truncate",
          online ? "text-muted-foreground" : "text-destructive",
        )}
      >
        {label}
      </span>
    </div>
  );
}

function safeT(
  t: ReturnType<typeof useTranslations>,
  key: string,
  fallback: string,
): string {
  try {
    const v = t(key);
    return v && v !== key ? v : fallback;
  } catch {
    return fallback;
  }
}
