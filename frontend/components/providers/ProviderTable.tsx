"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  ProviderRow,
  type ProviderRowData,
  type ProviderTestStatus,
} from "./ProviderRow";

export type { ProviderRowData, ProviderTestStatus };

export interface ProviderTableProps {
  providers: ProviderRowData[];
  onTestConnection: (name: string) => void;
  onToggleEnabled: (name: string, enabled: boolean) => void;
  onEditBaseUrl: (name: string, url: string) => void;
  testingName?: string;
  testResults?: Record<string, ProviderTestStatus>;
  className?: string;
}

const columns: Array<{ key: string; label: string; className?: string }> = [
  { key: "name", label: "Tên" },
  { key: "status", label: "Trạng thái" },
  { key: "baseUrl", label: "URL gốc" },
  { key: "enabled", label: "Kích hoạt" },
  { key: "test", label: "Kiểm tra" },
];

export function ProviderTable({
  providers,
  onTestConnection,
  onToggleEnabled,
  onEditBaseUrl,
  testingName,
  testResults,
  className,
}: ProviderTableProps) {
  return (
    <div
      className={cn(
        "overflow-x-auto rounded-xl bg-card ring-1 ring-foreground/10",
        className,
      )}
    >
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className={cn(
                  "px-3 py-2 text-left font-medium",
                  col.className,
                )}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {providers.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-3 py-8 text-center text-sm text-muted-foreground"
              >
                Chưa có nhà cung cấp.
              </td>
            </tr>
          ) : (
            providers.map((provider) => (
              <ProviderRow
                key={provider.name}
                data={provider}
                onTestConnection={onTestConnection}
                onToggleEnabled={onToggleEnabled}
                onEditBaseUrl={onEditBaseUrl}
                isTesting={testingName === provider.name}
                testResult={testResults?.[provider.name] ?? "idle"}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
