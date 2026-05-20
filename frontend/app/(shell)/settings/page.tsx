"use client";

/**
 * /settings — 4-tab settings page composing Designer's `SettingsTabs` shell
 * with RHF + zod form bodies. First-run wizard mounts here too; it opens
 * automatically when no API key is configured (see SettingsWizardController).
 *
 * Tab choice persists across reloads via `settings-store` (NEVER stores
 * secrets — only the last opened tab id and a "wizard dismissed" flag).
 */

import * as React from "react";

import { PageHero } from "@/components/common/PageHero";
import { ErrorState } from "@/components/common/ErrorState";
import {
  SettingsTabs,
  type SettingsTabItem,
} from "@/components/settings/SettingsTabs";
import { SettingsWizardController } from "@/components/settings/SettingsWizardController";
import { GeneralFormFields } from "@/components/settings/GeneralFormFields";
import { ApiKeysFormFields } from "@/components/settings/ApiKeysFormFields";
import { AdvancedL1FormFields } from "@/components/settings/AdvancedL1FormFields";
import { AdvancedL2FormFields } from "@/components/settings/AdvancedL2FormFields";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig } from "@/lib/api/queries";
import {
  useSettingsStore,
  type SettingsTabId,
} from "@/stores/settings-store";

function LoadingFallback() {
  return (
    <div className="flex flex-col gap-3" role="status" aria-live="polite">
      <Skeleton className="h-9 w-48" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

export default function SettingsPage() {
  const lastTab = useSettingsStore((s) => s.lastTab);
  const setLastTab = useSettingsStore((s) => s.setLastTab);
  const { data: config, isLoading, error, refetch } = useConfig();

  if (error) {
    return (
      <div className="flex flex-col gap-6">
        <PageHero title="Cài đặt" />
        <ErrorState
          title="Không tải được cài đặt"
          description={error.message}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  const tabs: SettingsTabItem[] = config
    ? [
        {
          id: "general",
          label: "Chung",
          content: <GeneralFormFields config={config} />,
        },
        {
          id: "api-keys",
          label: "Khóa API",
          content: <ApiKeysFormFields config={config} />,
        },
        {
          id: "advanced-l1",
          label: "Nâng cao L1",
          content: <AdvancedL1FormFields config={config} />,
        },
        {
          id: "advanced-l2",
          label: "Nâng cao L2",
          content: <AdvancedL2FormFields config={config} />,
        },
      ]
    : [];

  return (
    <div className="flex flex-col gap-6">
      <PageHero title="Cài đặt" />
      {isLoading || !config ? (
        <LoadingFallback />
      ) : (
        <>
          <SettingsTabs
            tabs={tabs}
            value={lastTab}
            onValueChange={(id) => setLastTab(id as SettingsTabId)}
          />
          <SettingsWizardController config={config} />
        </>
      )}
    </div>
  );
}
