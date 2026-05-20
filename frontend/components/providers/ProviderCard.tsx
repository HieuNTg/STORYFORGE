"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import type { ProviderRowData, ProviderTestStatus } from "./ProviderRow";

export interface ProviderCardProps {
  data: ProviderRowData;
  onTestConnection: (name: string) => void;
  onToggleEnabled: (name: string, enabled: boolean) => void;
  onEditBaseUrl: (name: string, url: string) => void;
  isTesting?: boolean;
  testResult?: ProviderTestStatus;
  className?: string;
}

const statusLabel: Record<ProviderTestStatus, string> = {
  idle: "Chưa kiểm tra",
  pass: "Đã xác minh",
  fail: "Lỗi kết nối",
};

const statusDot: Record<ProviderTestStatus, string> = {
  idle: "bg-muted-foreground/40",
  pass: "bg-emerald-500 shadow-[0_0_0_3px_rgba(16,185,129,0.18)]",
  fail: "bg-rose-500 shadow-[0_0_0_3px_rgba(244,63,94,0.18)]",
};

export function ProviderCard({
  data,
  onTestConnection,
  onToggleEnabled,
  onEditBaseUrl,
  isTesting = false,
  testResult = "idle",
  className,
}: ProviderCardProps) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(data.baseUrl ?? "");

  const startEdit = React.useCallback(() => {
    setDraft(data.baseUrl ?? "");
    setEditing(true);
  }, [data.baseUrl]);

  const commit = React.useCallback(() => {
    setEditing(false);
    const trimmed = draft.trim();
    if (trimmed !== (data.baseUrl ?? "")) {
      onEditBaseUrl(data.name, trimmed);
    }
  }, [draft, data.baseUrl, data.name, onEditBaseUrl]);

  const cancel = React.useCallback(() => {
    setEditing(false);
    setDraft(data.baseUrl ?? "");
  }, [data.baseUrl]);

  return (
    <article
      className={cn(
        "group flex flex-col gap-3 rounded-xl border border-accent/30 bg-card/50 p-4 transition-all",
        "hover:-translate-y-0.5 hover:border-accent hover:shadow-md",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col">
          <h3 className="truncate font-serif text-base text-foreground">
            {data.label ?? data.name}
          </h3>
          <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <span aria-hidden className={cn("size-2 rounded-full", statusDot[testResult])} />
            {statusLabel[testResult]}
          </span>
        </div>
        <Switch
          checked={data.enabled}
          onCheckedChange={(checked) => onToggleEnabled(data.name, checked)}
          aria-label={data.enabled ? "Đã kích hoạt" : "Đã tắt"}
        />
      </header>

      <div className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          URL gốc
        </span>
        {editing ? (
          <Input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commit();
              } else if (e.key === "Escape") {
                e.preventDefault();
                cancel();
              }
            }}
            placeholder="https://api.example.com"
            className="h-8 font-mono text-xs"
          />
        ) : (
          <button
            type="button"
            onClick={startEdit}
            className="truncate rounded-md bg-background/40 px-2 py-1 text-left font-mono text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {data.baseUrl?.trim() ? data.baseUrl : "Đặt URL gốc"}
          </button>
        )}
      </div>

      <footer className="mt-1 flex items-center justify-end">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isTesting}
          onClick={() => onTestConnection(data.name)}
        >
          {isTesting ? "Đang kiểm tra…" : "Kiểm tra"}
        </Button>
      </footer>
    </article>
  );
}
