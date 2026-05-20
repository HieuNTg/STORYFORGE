"use client";

/**
 * /providers — provider table with per-row test-connection, base URL edit,
 * and enabled toggle. Data comes from:
 *   - useConfig:         the canonical list of profiles + primary credentials
 *   - useProviderStatus: live availability + rate-limit (refresh every 30s)
 *   - useToggleProfile:  PATCH /api/config/profiles/{index}/toggle
 *   - useUpdateConfig:   PUT  /api/config (used for primary base URL edits)
 *   - useTestConnection: POST /api/config/test-connection
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
  useUpdateConfig,
  useToggleProfile,
  useTestConnection,
} from "@/lib/api/queries";

export default function ProvidersPage() {
  const { data: config, isLoading, error, refetch } = useConfig();
  const update = useUpdateConfig();
  const toggle = useToggleProfile();
  const test = useTestConnection();

  const [testingName, setTestingName] = React.useState<string | undefined>();
  const [testResults, setTestResults] = React.useState<
    Record<string, ProviderTestStatus>
  >({});

  const rows: ProviderRowData[] = React.useMemo(() => {
    if (!config) return [];
    const primary: ProviderRowData = {
      name: "__primary__",
      label: `Mặc định (${config.llm.model || "—"})`,
      enabled: true,
      baseUrl: config.llm.base_url,
      hasKey: Boolean(config.llm.api_key_masked),
    };
    const profiles: ProviderRowData[] = config.llm.profiles.map((p) => ({
      name: p.name,
      label: `${p.name} (${p.model})`,
      enabled: p.enabled,
      baseUrl: p.base_url,
      hasKey: Boolean(p.api_key_masked),
    }));
    return [primary, ...profiles];
  }, [config]);

  const handleEditBaseUrl = React.useCallback(
    async (name: string, url: string) => {
      if (name !== "__primary__") {
        toast.error("Chỉ chỉnh được URL của hồ sơ mặc định ở đây");
        return;
      }
      try {
        await update.mutateAsync({ base_url: url });
        toast.success("Đã cập nhật URL gốc");
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Cập nhật thất bại";
        toast.error(msg);
      }
    },
    [update],
  );

  const handleToggleEnabled = React.useCallback(
    async (name: string, _enabled: boolean) => {
      if (name === "__primary__") {
        toast.error("Không thể tắt hồ sơ mặc định");
        return;
      }
      const idx = config?.llm.profiles.findIndex((p) => p.name === name) ?? -1;
      if (idx < 0) return;
      try {
        await toggle.mutateAsync(idx);
      } catch (e) {
        const msg = e instanceof Error ? e.message : "Đổi trạng thái thất bại";
        toast.error(msg);
      }
    },
    [config, toggle],
  );

  const runTestAll = React.useCallback(async () => {
    setTestingName("__all__");
    try {
      const result = await test.mutateAsync();
      const next: Record<string, ProviderTestStatus> = {};
      for (const p of result.profiles) {
        next[p.name] = p.ok === true ? "pass" : p.ok === false ? "fail" : "idle";
      }
      // Map global ok onto __primary__ row (it isn't in profiles).
      next["__primary__"] = result.ok ? "pass" : "fail";
      setTestResults((prev) => ({ ...prev, ...next }));
      if (result.ok) {
        toast.success(result.message || "Kết nối thành công");
      } else {
        toast.error(result.message || "Một số hồ sơ kết nối thất bại");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Kiểm tra kết nối thất bại";
      toast.error(msg);
    } finally {
      setTestingName(undefined);
    }
  }, [test]);

  const handleTestConnection = React.useCallback(
    async (_name: string) => {
      // Backend exposes a single all-profiles test endpoint. We run it once
      // and demultiplex into the per-row map.
      await runTestAll();
    },
    [runTestAll],
  );

  if (error) {
    return (
      <div className="flex flex-col gap-6">
        <PageHero title="Nhà cung cấp" />
        <ErrorState
          title="Không tải được danh sách nhà cung cấp"
          description={error.message}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title="Nhà cung cấp"
        subtitle="Quản lý hồ sơ LLM và kiểm tra kết nối"
        actions={
          <Button
            type="button"
            variant="outline"
            onClick={runTestAll}
            disabled={testingName === "__all__" || test.isPending}
          >
            {testingName === "__all__"
              ? "Đang kiểm tra..."
              : "Kiểm tra tất cả"}
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
          testingName={testingName}
          testResults={testResults}
        />
      )}
    </div>
  );
}
