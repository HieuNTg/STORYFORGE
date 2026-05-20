"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import {
  type ProviderRowData,
  type ProviderTestStatus,
} from "./ProviderRow";
import { ProviderCard } from "./ProviderCard";

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

export function ProviderTable({
  providers,
  onTestConnection,
  onToggleEnabled,
  onEditBaseUrl,
  testingName,
  testResults,
  className,
}: ProviderTableProps) {
  if (providers.length === 0) {
    return (
      <div
        className={cn(
          "rounded-xl border border-dashed border-border bg-card/30 px-4 py-8 text-center text-sm text-muted-foreground",
          className,
        )}
      >
        Chưa có nhà cung cấp.
      </div>
    );
  }
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3",
        className,
      )}
    >
      {providers.map((provider) => (
        <ProviderCard
          key={provider.name}
          data={provider}
          onTestConnection={onTestConnection}
          onToggleEnabled={onToggleEnabled}
          onEditBaseUrl={onEditBaseUrl}
          isTesting={testingName === provider.name || testingName === "__all__"}
          testResult={testResults?.[provider.name] ?? "idle"}
        />
      ))}
    </div>
  );
}
