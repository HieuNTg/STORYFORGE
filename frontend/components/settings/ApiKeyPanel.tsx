"use client";

/**
 * ApiKeyPanel — read-only readout of configured providers with a single
 * "Kiểm tra tất cả" button that POSTs /api/config/test-connection.
 *
 * Per CLAUDE.md security policy (Rule 11 + memory `feedback_no_auth`):
 * keys live in env / config.json; this panel never accepts user input.
 * Inline editing lives in the existing settings tabs (ApiKeysFormFields)
 * — this panel is the at-a-glance status surface above them.
 */

import * as React from "react";
import { ShieldCheck, ShieldAlert, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useConfig, useTestConnection } from "@/lib/api/queries";

interface RowState {
  ok: boolean | null;
  message: string;
}

export function ApiKeyPanel() {
  const { data: config } = useConfig();
  const test = useTestConnection();
  const [results, setResults] = React.useState<Record<string, RowState>>({});

  const rows = React.useMemo(() => {
    if (!config) return [] as Array<{ name: string; provider: string; configured: boolean; model: string }>;
    return config.llm.profiles.map((p) => ({
      name: p.name,
      provider: p.provider,
      configured: Boolean(p.api_key_masked) && p.enabled,
      model: p.model,
    }));
  }, [config]);

  const handleTest = React.useCallback(async () => {
    try {
      const out = await test.mutateAsync();
      const next: Record<string, RowState> = {};
      for (const p of out.profiles) {
        next[p.name] = { ok: p.ok, message: p.message };
      }
      setResults(next);
      if (out.ok) toast.success("Tất cả nhà cung cấp OK");
      else toast.error(out.message || "Một số nhà cung cấp lỗi");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Kiểm tra thất bại";
      toast.error(msg);
    }
  }, [test]);

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-accent/30 bg-card/40 p-4">
      <header className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-serif text-lg text-foreground">Khóa API</h2>
          <p className="text-xs text-muted-foreground">
            Trạng thái nhà cung cấp · chỉ đọc · chỉnh sửa ở tab “Khóa API”
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={handleTest}
          disabled={test.isPending}
        >
          {test.isPending ? (
            <>
              <Loader2 className="size-3.5 animate-spin" /> Đang kiểm tra
            </>
          ) : (
            "Kiểm tra tất cả"
          )}
        </Button>
      </header>
      <ul className="flex flex-col gap-2">
        {rows.length === 0 ? (
          <li className="text-xs text-muted-foreground">Chưa cấu hình nhà cung cấp.</li>
        ) : (
          rows.map((r, index) => {
            const res = results[r.name];
            const ok = res?.ok ?? null;
            return (
              <li
                key={`${r.name}:${r.provider}:${r.model}:${index}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background/40 px-3 py-2"
              >
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-sm font-medium text-foreground">
                    {r.name}
                  </span>
                  <span className="truncate font-mono text-[11px] text-muted-foreground">
                    {r.model} · {r.provider}
                  </span>
                </div>
                <Badge
                  configured={r.configured}
                  ok={ok}
                  message={res?.message}
                />
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}

function Badge({
  configured,
  ok,
  message,
}: {
  configured: boolean;
  ok: boolean | null;
  message?: string;
}) {
  if (!configured) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
        <ShieldAlert className="size-3" /> Thiếu cấu hình
      </span>
    );
  }
  if (ok === true) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-500">
        <ShieldCheck className="size-3" /> OK
      </span>
    );
  }
  if (ok === false) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full bg-rose-500/10 px-2 py-0.5 text-xs text-rose-500",
        )}
        title={message}
      >
        <ShieldAlert className="size-3" /> Lỗi
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2 py-0.5 text-xs text-accent">
      <ShieldCheck className="size-3" /> Đã cấu hình
    </span>
  );
}
