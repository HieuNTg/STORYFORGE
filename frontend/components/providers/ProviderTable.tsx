"use client";

import * as React from "react";
import { cn } from "@/lib/utils";
import { useTranslations } from "next-intl";
import {
  type ProviderRowData,
  type ProviderTestStatus,
} from "./ProviderRow";
import { ProviderCard } from "./ProviderCard";

export type { ProviderRowData, ProviderTestStatus };

export interface ProviderEditPayload {
  name: string;
  base_url: string;
  api_key: string;
  model: string;
  enabled: boolean;
}

export interface ProviderTableProps {
  providers: ProviderRowData[];
  onTestConnection: (index: number) => void;
  onToggleEnabled: (index: number, enabled: boolean) => void;
  onEditBaseUrl: (index: number, url: string) => void;
  onEditProfile: (index: number, payload: ProviderEditPayload) => void;
  onDeleteProfile: (index: number) => void;
  testingIndex?: number | "__all__";
  testResults?: Record<number, ProviderTestStatus>;
  className?: string;
}

export function ProviderTable({
  providers,
  onTestConnection,
  onToggleEnabled,
  onEditBaseUrl,
  onEditProfile,
  onDeleteProfile,
  testingIndex,
  testResults,
  className,
}: ProviderTableProps) {
  const t = useTranslations("providers");

  if (providers.length === 0) {
    return (
      <div
        className={cn(
          "rounded-xl border border-dashed border-border bg-card/30 px-4 py-8 text-center text-sm text-muted-foreground",
          className,
        )}
      >
        {t("no_providers")}
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
          key={provider.index}
          data={provider}
          onTestConnection={onTestConnection}
          onToggleEnabled={onToggleEnabled}
          onEditBaseUrl={onEditBaseUrl}
          onEditProfile={onEditProfile}
          onDeleteProfile={onDeleteProfile}
          isTesting={
            testingIndex === provider.index || testingIndex === "__all__"
          }
          testResult={testResults?.[provider.index] ?? "idle"}
        />
      ))}
    </div>
  );
}
