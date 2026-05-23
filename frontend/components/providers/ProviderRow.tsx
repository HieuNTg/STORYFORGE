"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

export type ProviderTestStatus = "idle" | "pass" | "fail";

export interface ProviderRowData {
  /** Stable index into the backend fallback_models list — the real identity. */
  index: number;
  /** Provider display name (may collide across rows when two share a vendor). */
  name: string;
  /** Human-readable display label. */
  label?: string;
  /** Provider model id (used for the edit form). */
  model?: string;
  /** Whether the provider is enabled. */
  enabled: boolean;
  /** Base URL for API endpoint, editable. */
  baseUrl?: string;
  /** Whether the provider has a key configured (for status pill). */
  hasKey?: boolean;
}

export interface ProviderRowProps {
  data: ProviderRowData;
  onTestConnection: (name: string) => void;
  onToggleEnabled: (name: string, enabled: boolean) => void;
  onEditBaseUrl: (name: string, url: string) => void;
  isTesting?: boolean;
  testResult?: ProviderTestStatus;
}

const statusLabel: Record<ProviderTestStatus, string> = {
  idle: "Chưa kiểm tra",
  pass: "Đã xác minh",
  fail: "Lỗi kết nối",
};

const statusDotClass: Record<ProviderTestStatus, string> = {
  idle: "bg-muted-foreground/50",
  pass: "bg-accent",
  fail: "bg-destructive",
};

export function ProviderRow({
  data,
  onTestConnection,
  onToggleEnabled,
  onEditBaseUrl,
  isTesting = false,
  testResult = "idle",
}: ProviderRowProps) {
  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(data.baseUrl ?? "");

  React.useEffect(() => {
    if (!editing) setDraft(data.baseUrl ?? "");
  }, [data.baseUrl, editing]);

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
    <tr className="border-b last:border-b-0">
      <td className="px-3 py-2.5 align-middle">
        <span className="text-sm font-medium text-foreground">
          {data.label ?? data.name}
        </span>
      </td>
      <td className="px-3 py-2.5 align-middle">
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
          <span
            aria-hidden
            className={cn("size-1.5 rounded-full", statusDotClass[testResult])}
          />
          {statusLabel[testResult]}
        </span>
      </td>
      <td className="px-3 py-2.5 align-middle">
        {editing ? (
          <Input
            autoFocus
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onBlur={commit}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commit();
              } else if (event.key === "Escape") {
                event.preventDefault();
                cancel();
              }
            }}
            placeholder="https://api.example.com"
            className="h-7 font-mono text-xs"
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="w-full truncate rounded-md px-2 py-1 text-left font-mono text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            {data.baseUrl?.trim() ? data.baseUrl : "Đặt URL gốc"}
          </button>
        )}
      </td>
      <td className="px-3 py-2.5 align-middle">
        <div className="flex items-center gap-2">
          <Switch
            checked={data.enabled}
            onCheckedChange={(checked) => onToggleEnabled(data.name, checked)}
            aria-label={
              data.enabled ? "Đã kích hoạt" : "Đã tắt"
            }
          />
          <span className="text-xs text-muted-foreground">
            {data.enabled ? "Đã kích hoạt" : "Đã tắt"}
          </span>
        </div>
      </td>
      <td className="px-3 py-2.5 align-middle">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isTesting}
          onClick={() => onTestConnection(data.name)}
        >
          {isTesting ? "Đang kiểm tra..." : "Kiểm tra kết nối"}
        </Button>
      </td>
    </tr>
  );
}
