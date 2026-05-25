"use client";

/**
 * FeatureTogglesSettings — plain on/off panel for 4 PipelineConfig feature
 * flags exposed in the Settings UI.
 *
 * Wires:
 *   - enable_drama_climax        (default off)
 *   - enable_pipeline_overlay    (default on)
 *   - enable_chapter_illustration (default on)
 *   - enable_simulation_transcript (default on)
 *
 * Unlike `FlowkitSettings` (batched Save button + risk-ack gate), these are
 * plain switches that PUT immediately on change. No gate, no danger banner —
 * they're standard feature flags, not provider-enabling switches.
 *
 * Optimistic update: local state flips immediately, mutation fires, on error
 * we revert to the server-confirmed value and surface a toast.
 */

import * as React from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Switch } from "@/components/ui/switch";
import { useUpdateConfig } from "@/lib/api/queries";
import type { ConfigResponse, ConfigUpdate } from "@/lib/schemas/config";

export interface FeatureTogglesSettingsProps {
  config: ConfigResponse;
}

type ToggleKey =
  | "enable_drama_climax"
  | "enable_pipeline_overlay"
  | "enable_chapter_illustration"
  | "enable_simulation_transcript";

interface ToggleSpec {
  key: ToggleKey;
  labelKey: string;
  hintKey: string;
}

const TOGGLES: ToggleSpec[] = [
  {
    key: "enable_pipeline_overlay",
    labelKey: "form.features.overlay_label",
    hintKey: "form.features.overlay_hint",
  },
  {
    key: "enable_chapter_illustration",
    labelKey: "form.features.illust_label",
    hintKey: "form.features.illust_hint",
  },
  {
    key: "enable_simulation_transcript",
    labelKey: "form.features.sim_label",
    hintKey: "form.features.sim_hint",
  },
  {
    key: "enable_drama_climax",
    labelKey: "form.features.drama_label",
    hintKey: "form.features.drama_hint",
  },
];

export function FeatureTogglesSettings({ config }: FeatureTogglesSettingsProps) {
  const t = useTranslations("settings_panel");
  const update = useUpdateConfig();

  // Mirror server state in local component state so we can do optimistic flips
  // without waiting for the react-query invalidation round-trip. Reset whenever
  // the persisted values actually change.
  const serverValues = React.useMemo(
    () => ({
      enable_drama_climax: config.pipeline.enable_drama_climax,
      enable_pipeline_overlay: config.pipeline.enable_pipeline_overlay,
      enable_chapter_illustration: config.pipeline.enable_chapter_illustration,
      enable_simulation_transcript: config.pipeline.enable_simulation_transcript,
    }),
    [
      config.pipeline.enable_drama_climax,
      config.pipeline.enable_pipeline_overlay,
      config.pipeline.enable_chapter_illustration,
      config.pipeline.enable_simulation_transcript,
    ],
  );
  const serverKey = React.useMemo(() => JSON.stringify(serverValues), [serverValues]);
  const [local, setLocal] = React.useState(serverValues);
  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLocal(serverValues);
    // serverKey is the value-stable trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverKey]);

  // Track which keys are mid-flight so we can disable just that switch.
  const [pendingKey, setPendingKey] = React.useState<ToggleKey | null>(null);

  const onToggle = async (key: ToggleKey, next: boolean) => {
    const prev = local[key];
    if (prev === next) return;
    setLocal((s) => ({ ...s, [key]: next }));
    setPendingKey(key);
    try {
      const payload: ConfigUpdate = { [key]: next } as ConfigUpdate;
      await update.mutateAsync(payload);
      toast.success(t("form.save_success"));
    } catch (e) {
      // Revert optimistic flip on failure.
      setLocal((s) => ({ ...s, [key]: prev }));
      const msg = e instanceof Error ? e.message : t("form.save_failed");
      toast.error(msg);
    } finally {
      setPendingKey(null);
    }
  };

  return (
    <div className="mt-4 flex flex-col gap-4 rounded-lg border border-border bg-background p-4">
      <div className="flex flex-col">
        <h3 className="text-sm font-semibold text-foreground">{t("form.features.title")}</h3>
        <p className="text-xs text-muted-foreground">
          {t("form.features.desc")}
        </p>
      </div>

      <div className="flex flex-col gap-2">
        {TOGGLES.map((tSpec) => (
          <div
            key={tSpec.key}
            className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2"
          >
            <div className="flex flex-col">
              <span className="text-sm font-medium text-foreground">{t(tSpec.labelKey)}</span>
              <span className="text-xs text-muted-foreground">{t(tSpec.hintKey)}</span>
            </div>
            <Switch
              checked={local[tSpec.key]}
              onCheckedChange={(v) => void onToggle(tSpec.key, v)}
              disabled={pendingKey === tSpec.key}
              data-testid={`feature-toggle-${tSpec.key}`}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
