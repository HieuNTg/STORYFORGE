"use client";

/**
 * QwenLocalSettings — gated config panel for the local Qwen proxy provider.
 *
 * Render policy: only mounted when `image_provider === "qwen-local"`. Owns its
 * own draft state so the General tab's delta-only Save flow stays untouched,
 * mirroring `FlowkitSettings`.
 *
 * The API key field follows the same contract as every other secret in this
 * app: the backend only ever returns a masked value, and an empty field means
 * "leave the stored key alone" (see `save_config` in api/config_routes.py).
 */

import * as React from "react";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useQwenLocalStatus, useUpdateConfig } from "@/lib/api/queries";
import { QWEN_LOCAL_SIZES, type ConfigResponse } from "@/lib/schemas/config";

export interface QwenLocalSettingsProps {
  config: ConfigResponse;
}

type QwenLocalDraft = {
  qwen_local_base_url: string;
  qwen_local_api_key: string;
  qwen_local_model: string;
  qwen_local_size: string;
  qwen_local_use_edit_for_refs: boolean;
  qwen_local_timeout: number;
};

function snapshot(p: ConfigResponse["pipeline"]): QwenLocalDraft {
  return {
    qwen_local_base_url: p.qwen_local_base_url,
    // Never seeded from the masked value — an untouched field must stay empty
    // so the diff below leaves the stored key alone.
    qwen_local_api_key: "",
    qwen_local_model: p.qwen_local_model,
    qwen_local_size: p.qwen_local_size,
    qwen_local_use_edit_for_refs: p.qwen_local_use_edit_for_refs,
    qwen_local_timeout: p.qwen_local_timeout,
  };
}

function diff(a: QwenLocalDraft, b: QwenLocalDraft): Partial<QwenLocalDraft> {
  const out: Partial<QwenLocalDraft> = {};
  (Object.keys(a) as Array<keyof QwenLocalDraft>).forEach((k) => {
    if (a[k] !== b[k]) (out as Record<string, unknown>)[k] = a[k];
  });
  return out;
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

function StatusBadge({
  loading,
  reachable,
  ready,
}: {
  loading: boolean;
  reachable?: boolean;
  ready?: boolean;
}) {
  const t = useTranslations("settings_panel");
  if (loading) return <Badge variant="secondary">{t("form.qwen_local.status_checking")}</Badge>;
  if (ready) return <Badge variant="default">{t("form.qwen_local.status_ready")}</Badge>;
  if (reachable)
    return <Badge variant="secondary">{t("form.qwen_local.status_no_qwen")}</Badge>;
  return <Badge variant="destructive">{t("form.qwen_local.status_offline")}</Badge>;
}

export function QwenLocalSettings({ config }: QwenLocalSettingsProps) {
  const t = useTranslations("settings_panel");
  const update = useUpdateConfig();
  // Stable serialized key so a background refetch with identical values does
  // NOT clobber in-flight draft edits (same reasoning as FlowkitSettings).
  const initial = React.useMemo(() => snapshot(config.pipeline), [config]);
  const initialKey = React.useMemo(() => JSON.stringify(initial), [initial]);
  const [draft, setDraft] = React.useState<QwenLocalDraft>(initial);
  React.useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDraft(initial);
    // initial intentionally excluded — initialKey is the value-stable trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialKey]);

  const status = useQwenLocalStatus(true);
  const dirtyPayload = diff(draft, initial);
  const isDirty = Object.keys(dirtyPayload).length > 0;
  const maskedKey = config.pipeline.qwen_local_api_key_masked;

  const onSave = async () => {
    if (!isDirty) {
      toast.success(t("form.no_changes"));
      return;
    }
    try {
      await update.mutateAsync(dirtyPayload);
      toast.success(t("form.qwen_local.save_success"));
      status.refetch();
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("form.save_failed");
      toast.error(msg);
    }
  };

  const set = <K extends keyof QwenLocalDraft>(k: K, v: QwenLocalDraft[K]) =>
    setDraft((d) => ({ ...d, [k]: v }));

  return (
    <div
      className="mt-4 flex flex-col gap-4 rounded-lg border border-border bg-background p-4"
      data-testid="qwen-local-settings"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex flex-col">
          <h3 className="text-sm font-semibold text-foreground">
            {t("form.qwen_local.title")}
          </h3>
          <p className="text-xs text-muted-foreground">{t("form.qwen_local.desc")}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <StatusBadge
            loading={status.isFetching && status.data == null}
            reachable={status.data?.reachable}
            ready={status.data?.qwen_ready}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => status.refetch()}
            disabled={status.isFetching}
            data-testid="qwen-local-recheck"
          >
            {t("form.qwen_local.recheck")}
          </Button>
        </div>
      </div>

      {status.data?.error ? (
        <p className="rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
          {status.data.error}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Labeled
          label={t("form.qwen_local.base_url_label")}
          hint={t("form.qwen_local.base_url_hint")}
        >
          <Input
            value={draft.qwen_local_base_url}
            onChange={(e) => set("qwen_local_base_url", e.target.value)}
            placeholder="http://localhost:8000/v1"
            data-testid="qwen-local-base-url"
          />
        </Labeled>
        <Labeled
          label={t("form.qwen_local.api_key_label")}
          hint={
            maskedKey
              ? t("form.qwen_local.api_key_hint_set", { masked: maskedKey })
              : t("form.qwen_local.api_key_hint")
          }
        >
          <Input
            type="password"
            value={draft.qwen_local_api_key}
            onChange={(e) => set("qwen_local_api_key", e.target.value)}
            placeholder={maskedKey || "changeme-internal-key"}
            data-testid="qwen-local-api-key"
          />
        </Labeled>
        <Labeled
          label={t("form.qwen_local.model_label")}
          hint={t("form.qwen_local.model_hint")}
        >
          <Input
            value={draft.qwen_local_model}
            onChange={(e) => set("qwen_local_model", e.target.value)}
            placeholder="qwen3.8-max-image"
            data-testid="qwen-local-model"
          />
        </Labeled>
        <Labeled
          label={t("form.qwen_local.size_label")}
          hint={t("form.qwen_local.size_hint")}
        >
          <Select
            value={draft.qwen_local_size || "auto"}
            onValueChange={(v) =>
              set("qwen_local_size", !v || v === "auto" ? "" : v)
            }
          >
            <SelectTrigger data-testid="qwen-local-size">
              {/* Explicit children: the empty ("auto") option's label is a
                  translated string, which SelectValue cannot infer on its own. */}
              <SelectValue>
                {draft.qwen_local_size || t("form.qwen_local.size_auto")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {QWEN_LOCAL_SIZES.map((size) => (
                <SelectItem key={size || "auto"} value={size || "auto"}>
                  {size || t("form.qwen_local.size_auto")}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Labeled>
        <Labeled
          label={t("form.qwen_local.timeout_label")}
          hint={t("form.qwen_local.timeout_hint")}
        >
          <Input
            type="number"
            min={30}
            max={900}
            value={draft.qwen_local_timeout}
            onChange={(e) => set("qwen_local_timeout", Number(e.target.value))}
            data-testid="qwen-local-timeout"
          />
        </Labeled>
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-border pt-4">
        <div className="flex flex-col">
          <label className="text-sm font-medium text-foreground">
            {t("form.qwen_local.edit_refs_label")}
          </label>
          <span className="text-xs text-muted-foreground">
            {t("form.qwen_local.edit_refs_desc")}
          </span>
        </div>
        <Switch
          checked={draft.qwen_local_use_edit_for_refs}
          onCheckedChange={(v) => set("qwen_local_use_edit_for_refs", v)}
          data-testid="qwen-local-edit-refs"
        />
      </div>

      <div className="flex justify-end">
        <Button
          type="button"
          onClick={onSave}
          disabled={!isDirty || update.isPending}
          data-testid="qwen-local-save"
        >
          {update.isPending ? t("form.saving") : t("form.save")}
        </Button>
      </div>
    </div>
  );
}
