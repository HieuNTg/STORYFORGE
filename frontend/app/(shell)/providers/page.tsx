"use client";

/**
 * /providers — provider table with per-row test-connection, base URL edit,
 * enabled toggle, edit, and delete. Data comes from:
 *   - useConfig:         the canonical list of profiles + primary credentials
 *   - useToggleProfile:  PATCH  /api/config/profiles/{index}/toggle
 *   - useUpdateProfile:  PUT    /api/config/profiles/{index} (full replace)
 *   - useDeleteProfile:  DELETE /api/config/profiles/{index}
 *   - useTestConnection: POST   /api/config/test-connection
 *
 * Rows are identified by their `index` into `config.llm.profiles`, NOT by
 * `name` — multiple profiles can share a vendor name (e.g. two "Google Gemini"
 * fallbacks) which would otherwise collide as React keys and corrupt
 * per-row state. The backend addresses profiles by index too, so this is the
 * stable identity end-to-end.
 *
 * `test-connection` is a global probe — it returns per-profile pass/fail
 * once. We surface that as the per-row `testResult` map.
 */

import * as React from "react";
import { toast } from "sonner";

import { PageHero } from "@/components/common/PageHero";
import { ErrorState } from "@/components/common/ErrorState";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  ProviderTable,
  type ProviderRowData,
  type ProviderTestStatus,
} from "@/components/providers/ProviderTable";
import {
  useConfig,
  useToggleProfile,
  useUpdateProfile,
  useDeleteProfile,
  useTestConnection,
} from "@/lib/api/queries";
import type { ProviderEditPayload } from "@/components/providers/ProviderTable";

import { useTranslations } from "next-intl";

export default function ProvidersPage() {
  const t = useTranslations("providers");
  const { data: config, isLoading, error, refetch } = useConfig();
  const toggle = useToggleProfile();
  const updateProfile = useUpdateProfile();
  const deleteProfile = useDeleteProfile();
  const test = useTestConnection();

  const [testingIndex, setTestingIndex] = React.useState<
    number | "__all__" | undefined
  >();
  // Per-row test status, keyed by profile index. Index is stable for the
  // lifetime of a config snapshot — when profiles are added/removed the
  // backend reissues fresh indices and React Query invalidation resets state.
  const [testResults, setTestResults] = React.useState<
    Record<number, ProviderTestStatus>
  >({});

  // Hydrate testResults from the per-profile `last_test_ok` persisted by the
  // backend so a passing test survives a page refresh. In-session results
  // (set by `runTestAll`) take precedence over the persisted snapshot.
  React.useEffect(() => {
    if (!config) return;
    setTestResults((prev) => {
      const next = { ...prev };
      config.llm.profiles.forEach((p, idx) => {
        if (next[idx] && next[idx] !== "idle") return;
        if (p.last_test_ok === true) next[idx] = "pass";
        else if (p.last_test_ok === false) next[idx] = "fail";
      });
      return next;
    });
  }, [config]);

  const rows: ProviderRowData[] = React.useMemo(() => {
    if (!config) return [];
    return config.llm.profiles.map((p, idx) => ({
      index: idx,
      name: p.name,
      label: `${p.name} (${p.model})`,
      model: p.model,
      enabled: p.enabled,
      baseUrl: p.base_url,
      hasKey: Boolean(p.api_key_masked),
    }));
  }, [config]);

  const handleEditBaseUrl = React.useCallback(
    async (index: number, url: string) => {
      const profile = config?.llm.profiles[index];
      if (!profile) return;
      try {
        await updateProfile.mutateAsync({
          index,
          name: profile.name,
          base_url: url,
          api_key: "",
          model: profile.model,
          enabled: profile.enabled,
        });
        toast.success(t("update_url_success"));
      } catch (e) {
        const msg = e instanceof Error ? e.message : t("update_failed");
        toast.error(msg);
      }
    },
    [config, updateProfile, t],
  );

  const handleToggleEnabled = React.useCallback(
    async (index: number, _enabled: boolean) => {
      if (!config?.llm.profiles[index]) return;
      try {
        await toggle.mutateAsync(index);
      } catch (e) {
        const msg = e instanceof Error ? e.message : t("toggle_status_failed");
        toast.error(msg);
      }
    },
    [config, toggle, t],
  );

  const handleEditProfile = React.useCallback(
    async (index: number, payload: ProviderEditPayload) => {
      try {
        await updateProfile.mutateAsync({ index, ...payload });
        toast.success(t("update_provider_success"));
      } catch (e) {
        const msg = e instanceof Error ? e.message : t("update_failed");
        toast.error(msg);
      }
    },
    [updateProfile, t],
  );

  const handleDeleteProfile = React.useCallback(
    async (index: number) => {
      try {
        await deleteProfile.mutateAsync(index);
        setTestResults((prev) => {
          // Drop the deleted index and shift everything above it down by one
          // so persisted per-row status stays aligned with the new list.
          const next: Record<number, ProviderTestStatus> = {};
          for (const [k, v] of Object.entries(prev)) {
            const i = Number(k);
            if (i === index) continue;
            next[i > index ? i - 1 : i] = v;
          }
          return next;
        });
        toast.success(t("delete_provider_success"));
      } catch (e) {
        const msg = e instanceof Error ? e.message : t("delete_failed");
        toast.error(msg);
      }
    },
    [deleteProfile, t],
  );

  const runTestAll = React.useCallback(async () => {
    setTestingIndex("__all__");
    try {
      const result = await test.mutateAsync();
      // Backend returns results in the order [primary, ...fallback_models],
      // so skip the leading "Primary" entry to align with profile indices.
      const next: Record<number, ProviderTestStatus> = {};
      result.profiles.slice(1).forEach((p, idx) => {
        next[idx] = p.ok === true ? "pass" : p.ok === false ? "fail" : "idle";
      });
      setTestResults((prev) => ({ ...prev, ...next }));
      if (result.ok) {
        toast.success(result.message || t("connect_success"));
      } else {
        toast.error(result.message || t("connect_some_failed"));
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("connect_test_failed");
      toast.error(msg);
    } finally {
      setTestingIndex(undefined);
    }
  }, [test, t]);

  const handleTestConnection = React.useCallback(
    async (_index: number) => {
      // Backend exposes a single all-profiles test endpoint. We run it once
      // and demultiplex into the per-row map.
      await runTestAll();
    },
    [runTestAll],
  );

  if (error) {
    return (
      <div className="flex flex-col gap-6">
        <PageHero title={t("title")} />
        <ErrorState
          title={t("load_failed")}
          description={error.message}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title={t("title")}
        subtitle={t("subtitle")}
        actions={
          <Button
            type="button"
            variant="outline"
            onClick={runTestAll}
            disabled={testingIndex === "__all__" || test.isPending}
          >
            {testingIndex === "__all__"
              ? t("testing_all")
              : t("test_all")}
          </Button>
        }
      />
      {isLoading || !config ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <ProviderTable
          providers={rows}
          onTestConnection={handleTestConnection}
          onToggleEnabled={handleToggleEnabled}
          onEditBaseUrl={handleEditBaseUrl}
          onEditProfile={handleEditProfile}
          onDeleteProfile={handleDeleteProfile}
          testingIndex={testingIndex}
          testResults={testResults}
        />
      )}
    </div>
  );
}
