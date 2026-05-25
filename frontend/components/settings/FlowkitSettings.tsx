"use client";

/**
 * FlowkitSettings — gated config panel for the FlowKit (Google Labs) provider.
 *
 * Render policy: only mounted when `image_provider === "flowkit"`. Owns its own
 * RHF form so the General tab's delta-only Save flow stays untouched. Every
 * interactive control beyond the risk-ack checkbox is disabled until
 * `flowkit_risk_acknowledged` is true — mirrors the backend hard gate in
 * `api/config_routes.py`.
 */

import * as React from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { useFlowkitStatus, useUpdateConfig } from "@/lib/api/queries";
import type { ConfigResponse } from "@/lib/schemas/config";

export interface FlowkitSettingsProps {
  config: ConfigResponse;
}

type FlowkitDraft = {
  flowkit_risk_acknowledged: boolean;
  flowkit_enabled: boolean;
  flowkit_port: number;
  flowkit_style_reference_path: string;
  flowkit_use_refiner: boolean;
  flowkit_request_timeout: number;
  flowkit_concurrent_workers_max: number;
  flowkit_workers_ramp_threshold: number;
  flowkit_veo_poll_interval: number;
  flowkit_image_input_type_split: boolean;
  flowkit_callback_hmac_required: boolean;
};

function snapshot(p: ConfigResponse["pipeline"]): FlowkitDraft {
  return {
    flowkit_risk_acknowledged: p.flowkit_risk_acknowledged,
    flowkit_enabled: p.flowkit_enabled,
    flowkit_port: p.flowkit_port,
    flowkit_style_reference_path: p.flowkit_style_reference_path,
    flowkit_use_refiner: p.flowkit_use_refiner,
    flowkit_request_timeout: p.flowkit_request_timeout,
    flowkit_concurrent_workers_max: p.flowkit_concurrent_workers_max,
    flowkit_workers_ramp_threshold: p.flowkit_workers_ramp_threshold,
    flowkit_veo_poll_interval: p.flowkit_veo_poll_interval,
    flowkit_image_input_type_split: p.flowkit_image_input_type_split,
    flowkit_callback_hmac_required: p.flowkit_callback_hmac_required,
  };
}

function diff(a: FlowkitDraft, b: FlowkitDraft): Partial<FlowkitDraft> {
  const out: Partial<FlowkitDraft> = {};
  (Object.keys(a) as Array<keyof FlowkitDraft>).forEach((k) => {
    if (a[k] !== b[k]) (out as Record<string, unknown>)[k] = a[k];
  });
  return out;
}

export function FlowkitSettings({ config }: FlowkitSettingsProps) {
  const t = useTranslations("settings_panel");
  const update = useUpdateConfig();
  // Stable serialized key so a background refetch with identical values does
  // NOT clobber in-flight draft edits. Only resets when persisted state actually
  // changes (e.g., after a save round-trip).
  const initial = React.useMemo(() => snapshot(config.pipeline), [config]);
  const initialKey = React.useMemo(() => JSON.stringify(initial), [initial]);
  const [draft, setDraft] = React.useState<FlowkitDraft>(initial);
  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(initial);
    // initial intentionally excluded — initialKey is the value-stable trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialKey]);

  const status = useFlowkitStatus(initial.flowkit_enabled);
  const acked = draft.flowkit_risk_acknowledged;
  const dirtyPayload = diff(draft, initial);
  const isDirty = Object.keys(dirtyPayload).length > 0;

  const onSave = async () => {
    if (!isDirty) {
      toast.success(t("form.no_changes"));
      return;
    }
    try {
      await update.mutateAsync(dirtyPayload);
      toast.success(t("form.flowkit.save_success"));
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("form.save_failed");
      toast.error(msg);
    }
  };

  const set = <K extends keyof FlowkitDraft>(k: K, v: FlowkitDraft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div className="mt-4 flex flex-col gap-4 rounded-lg border border-border bg-background p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col">
          <h3 className="text-sm font-semibold text-foreground">{t("form.flowkit.title")}</h3>
          <p className="text-xs text-muted-foreground">
            {t("form.flowkit.desc")}
          </p>
        </div>
        <FlowkitStatusBadge
          enabled={initial.flowkit_enabled}
          connected={status.data?.connected}
          loading={status.isFetching && status.data == null}
        />
      </div>

      <div className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs text-destructive">
        <strong className="font-semibold">{t("form.flowkit.warning_title")}</strong>{" "}
        {t("form.flowkit.warning_body")}
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-destructive"
          checked={draft.flowkit_risk_acknowledged}
          onChange={(e) => set("flowkit_risk_acknowledged", e.target.checked)}
          data-testid="flowkit-risk-ack"
        />
        <span>
          {t("form.flowkit.ack_label")}
        </span>
      </label>

      <fieldset
        disabled={!acked}
        className={cn(
          "flex flex-col gap-4 border-t border-border pt-4",
          !acked && "opacity-50",
        )}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="flex flex-col">
            <label className="text-sm font-medium text-foreground">
              {t("form.flowkit.enable_label")}
            </label>
            <span className="text-xs text-muted-foreground">
              {t("form.flowkit.enable_desc")}
            </span>
          </div>
          <Switch
            checked={draft.flowkit_enabled}
            onCheckedChange={(v) => set("flowkit_enabled", v)}
            data-testid="flowkit-enabled"
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Labeled label={t("form.flowkit.port_label")} hint={t("form.flowkit.port_hint")}>
            <Input
              type="number"
              min={1024}
              max={65535}
              value={draft.flowkit_port}
              onChange={(e) => set("flowkit_port", Number(e.target.value))}
            />
          </Labeled>
          <Labeled label={t("form.flowkit.timeout_label")} hint={t("form.flowkit.timeout_hint")}>
            <Input
              type="number"
              min={30}
              max={900}
              value={draft.flowkit_request_timeout}
              onChange={(e) =>
                set("flowkit_request_timeout", Number(e.target.value))
              }
            />
          </Labeled>
          <Labeled label={t("form.flowkit.workers_label")} hint={t("form.flowkit.workers_hint")}>
            <Input
              type="number"
              min={1}
              max={10}
              value={draft.flowkit_concurrent_workers_max}
              onChange={(e) =>
                set("flowkit_concurrent_workers_max", Number(e.target.value))
              }
            />
          </Labeled>
          <Labeled
            label={t("form.flowkit.ramp_label")}
            hint={t("form.flowkit.ramp_hint")}
          >
            <Input
              type="number"
              min={1}
              max={50}
              value={draft.flowkit_workers_ramp_threshold}
              onChange={(e) =>
                set("flowkit_workers_ramp_threshold", Number(e.target.value))
              }
            />
          </Labeled>
          <Labeled label={t("form.flowkit.veo_label")} hint={t("form.flowkit.veo_hint")}>
            <Input
              type="number"
              min={1}
              max={60}
              step={0.5}
              value={draft.flowkit_veo_poll_interval}
              onChange={(e) =>
                set("flowkit_veo_poll_interval", Number(e.target.value))
              }
            />
          </Labeled>
          <Labeled
            label={t("form.flowkit.ref_label")}
            hint={t("form.flowkit.ref_hint")}
          >
            <Input
              type="text"
              placeholder={t("form.flowkit.ref_placeholder")}
              value={draft.flowkit_style_reference_path}
              onChange={(e) =>
                set("flowkit_style_reference_path", e.target.value)
              }
            />
          </Labeled>
        </div>

        <Toggle
          label={t("form.flowkit.refiner_label")}
          hint={t("form.flowkit.refiner_hint")}
          checked={draft.flowkit_use_refiner}
          onChange={(v) => set("flowkit_use_refiner", v)}
        />
        <Toggle
          label={t("form.flowkit.split_label")}
          hint={t("form.flowkit.split_hint")}
          checked={draft.flowkit_image_input_type_split}
          onChange={(v) => set("flowkit_image_input_type_split", v)}
        />
        <Toggle
          label={t("form.flowkit.hmac_label")}
          hint={t("form.flowkit.hmac_hint")}
          checked={draft.flowkit_callback_hmac_required}
          onChange={(v) => set("flowkit_callback_hmac_required", v)}
        />

        {status.data ? (
          <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
            <div>
              Workers: <span className="font-mono">{status.data.workers_current}</span>
              {" / "}
              <span className="font-mono">{status.data.workers_max}</span>
            </div>
            <div>
              Pending WS: <span className="font-mono">{status.data.pending_ws_requests}</span>
              {" — Poll: "}
              <span className="font-mono">{status.data.poll_running ? "ON" : "off"}</span>
              {" — Token age: "}
              <span className="font-mono">
                {status.data.last_token_age_s < 0 ? "—" : `${status.data.last_token_age_s}s`}
              </span>
            </div>
          </div>
        ) : null}
      </fieldset>

      <div className="flex items-center justify-end gap-2 border-t border-border pt-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setDraft(initial)}
          disabled={!isDirty || update.isPending}
        >
          {t("form.flowkit.undo")}
        </Button>
        <Button
          size="sm"
          onClick={() => void onSave()}
          disabled={!isDirty || update.isPending}
        >
          {update.isPending ? t("form.saving") : t("form.flowkit.save_flowkit")}
        </Button>
      </div>
    </div>
  );
}

function Labeled({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-foreground">{label}</label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

function Toggle({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2">
      <div className="flex flex-col">
        <span className="text-sm font-medium text-foreground">{label}</span>
        {hint ? (
          <span className="text-xs text-muted-foreground">{hint}</span>
        ) : null}
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

function FlowkitStatusBadge({
  enabled,
  connected,
  loading,
}: {
  enabled: boolean;
  connected?: boolean;
  loading: boolean;
}) {
  const t = useTranslations("settings_panel");
  if (!enabled) return <Badge variant="outline">{t("form.flowkit.status_disabled")}</Badge>;
  if (loading) return <Badge variant="outline">{t("form.flowkit.status_checking")}</Badge>;
  if (connected) return <Badge className="bg-emerald-600 text-white">{t("form.flowkit.status_connected")}</Badge>;
  return <Badge variant="destructive">{t("form.flowkit.status_disconnected")}</Badge>;
}
