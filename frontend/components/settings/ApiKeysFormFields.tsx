"use client";

/**
 * ApiKeysFormFields â€” RHF body for the "API Keys" settings tab.
 *
 * SECURITY INVARIANTS (do not relax without security review):
 *   1. Secret values live in RHF state ONLY. Never serialized to URL (nuqs),
 *      never written to Zustand persist, never logged.
 *   2. Inputs render as `type="password"` by default. Designer's `MaskedInput`
 *      flips to text on an explicit click â€” never automatically.
 *   3. PUT payload is delta-only â€” built from RHF `dirtyFields`. The masked
 *      echo never appears in `dirtyFields` because the user never typed it,
 *      so it cannot be sent back as a "new" key (F4/F5).
 *   4. The masked echo (e.g. `sk-1***abcd`) from GET /api/config is shown as
 *      a hint, never prefilled into the writable input.
 */

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { ApiKeysForm, MaskedInput } from "@/components/settings/ApiKeysForm";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  apiKeysFormSchema,
  type ApiKeysFormValues,
  type ConfigResponse,
  type ConfigUpdate,
} from "@/lib/schemas/config";
import { apiFetch } from "@/lib/api/client";
import { useUpdateConfig, useProviderPresets } from "@/lib/api/queries";
import { pickDirty } from "@/lib/forms/dirty";

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

interface ProviderPreset {
  name: string;
  label: string;
  baseUrl: string;
  model: string;
  models: Array<{ id: string; label: string }>;
  placeholder: string;
}

// Provider cards are served by the backend (single source of truth) —
// GET /api/config/provider-presets, see config/presets.py::PROVIDER_PRESETS.
// The hook returns snake_case DTOs; map `base_url` → `baseUrl` for this view.

export interface ApiKeysFormFieldsProps {
  config: ConfigResponse;
}

export function ApiKeysFormFields({ config }: ApiKeysFormFieldsProps) {
  const t = useTranslations("settings_panel");
  const update = useUpdateConfig();
  const queryClient = useQueryClient();
  const [providerKeys, setProviderKeys] = React.useState<Record<string, string>>({});
  const [providerModels, setProviderModels] = React.useState<Record<string, string>>({});
  const [savingProvider, setSavingProvider] = React.useState<string | null>(null);

  // Provider cards come from the backend (single source of truth). Map the
  // snake_case DTO onto the camelCase shape this component renders with.
  const providerPresetsQuery = useProviderPresets();
  const providerPresets = React.useMemo<ProviderPreset[]>(
    () =>
      (providerPresetsQuery.data ?? []).map((p) => ({
        name: p.name,
        label: p.label,
        baseUrl: p.base_url,
        model: p.model,
        models: p.models,
        placeholder: p.placeholder,
      })),
    [providerPresetsQuery.data],
  );

  // IMPORTANT: defaults start empty for secrets. Showing the masked echo as a
  // value would let the user accidentally "save" the masked string back.
  const defaults: ApiKeysFormValues = React.useMemo(
    () => ({
      api_key: "",
      base_url: config.llm.base_url || "https://api.openai.com/v1",
      hf_token: "",
    }),
    [config],
  );

  const form = useForm<ApiKeysFormValues>({
    resolver: zodResolver(apiKeysFormSchema),
    defaultValues: defaults,
  });

  React.useEffect(() => {
    form.reset(defaults);
  }, [defaults, form]);

  const onSave = form.handleSubmit(async (values) => {
    // Delta-only PUT: build payload from RHF dirtyFields. A masked echo
    // (e.g. `sk-1***abcd`) is never in `dirtyFields` because the user did
    // not type it, so it can never round-trip as a "new" key (F4/F5).
    const dirty = pickDirty(values, form.formState.dirtyFields);
    const payload: ConfigUpdate = {};
    if (typeof dirty.base_url === "string") payload.base_url = dirty.base_url;
    if (typeof dirty.api_key === "string" && dirty.api_key.trim().length > 0) {
      payload.api_key = dirty.api_key;
    }
    if (typeof dirty.hf_token === "string" && dirty.hf_token.trim().length > 0) {
      payload.hf_token = dirty.hf_token;
    }

    // Nothing actually changed → skip the request entirely.
    if (Object.keys(payload).length === 0) {
      toast.success(t("form.no_changes"));
      return;
    }

    try {
      await update.mutateAsync(payload);
      // Clear secret fields immediately after a successful save so they
      // don't linger in component state any longer than necessary.
      form.reset({ ...values, api_key: "", hf_token: "" });
      toast.success(t("form.api.save_success"));
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("form.save_failed");
      toast.error(msg);
    }
  });

  const errors = form.formState.errors;
  const hfMasked = config.pipeline.hf_token_masked;

  const profileByName = React.useMemo(() => {
    const map = new Map<string, ConfigResponse["llm"]["profiles"][number]>();
    for (const profile of config.llm.profiles) map.set(profile.name, profile);
    return map;
  }, [config.llm.profiles]);

  async function saveProvider(preset: ProviderPreset) {
    const apiKey = providerKeys[preset.name]?.trim() ?? "";
    if (!apiKey) {
      toast.error(t("form.api.enter_key_first", { provider: preset.label }));
      return;
    }
    setSavingProvider(preset.name);
    try {
      await apiFetch("/api/config/profiles", {
        method: "POST",
        body: JSON.stringify({
          name: preset.name,
          base_url: preset.baseUrl,
          api_key: apiKey,
          model: providerModels[preset.name] || preset.model,
          enabled: true,
        }),
      });
      setProviderKeys((prev) => ({ ...prev, [preset.name]: "" }));
      await queryClient.invalidateQueries({ queryKey: ["config"] });
      toast.success(t("form.api.saved_preset", { provider: preset.label }));
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("form.api.save_preset_failed");
      toast.error(msg);
    } finally {
      setSavingProvider(null);
    }
  }

  return (
    <ApiKeysForm
      isSaving={update.isPending}
      onSave={onSave}
      canReset={form.formState.isDirty}
      onReset={() => form.reset(defaults)}
      form={
        <div className="flex flex-col gap-5">
          <section className="rounded-lg border border-border/70 bg-background/40 p-4">
            <div className="mb-3">
              <h3 className="text-sm font-medium text-foreground">{t("form.api.quick_provider")}</h3>
              <p className="text-xs text-muted-foreground">
                {t("form.api.quick_provider_desc")}
              </p>
            </div>
            {providerPresetsQuery.isLoading && providerPresets.length === 0 ? (
              <p className="text-xs text-muted-foreground">{t("form.api.loading_providers")}</p>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {providerPresets.map((preset) => {
                const existing = profileByName.get(preset.name);
                const busy = savingProvider === preset.name;
                return (
                  <div
                    key={preset.name}
                    className="rounded-md border border-border bg-card/60 p-3"
                  >
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <div>
                        <div className="text-sm font-medium text-foreground">{preset.label}</div>
                        <select
                          value={providerModels[preset.name] || existing?.model || preset.model}
                          onChange={(e) =>
                            setProviderModels((prev) => ({
                              ...prev,
                              [preset.name]: e.target.value,
                            }))
                          }
                          className="mt-1 h-8 max-w-56 rounded-md border border-input bg-background px-2 font-mono text-[11px] text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          aria-label={t("form.api.model_select_label", { provider: preset.label })}
                        >
                          {preset.models.map((model) => (
                            <option key={model.id} value={model.id}>
                              {model.label}
                            </option>
                          ))}
                        </select>
                      </div>
                      <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                        {existing?.api_key_masked ? t("api.configured") : t("api.missing")}
                      </span>
                    </div>
                    <Input
                      type="password"
                      autoComplete="off"
                      value={providerKeys[preset.name] ?? ""}
                      onChange={(e) =>
                        setProviderKeys((prev) => ({
                          ...prev,
                          [preset.name]: e.target.value,
                        }))
                      }
                      placeholder={
                        existing?.api_key_masked
                          ? t("form.api.existing_key_hint", { masked: existing.api_key_masked })
                          : preset.placeholder
                      }
                    />
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <span className="truncate font-mono text-[10px] text-muted-foreground">
                        {preset.baseUrl}
                      </span>
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy || !(providerKeys[preset.name] ?? "").trim()}
                        onClick={() => saveProvider(preset)}
                      >
                        {busy ? t("form.saving") : existing ? t("update") : t("add")}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <div className="flex flex-col gap-1.5">
            <MaskedInput
              label={t("form.api.huggingface_label")}
              value={form.watch("hf_token")}
              onChange={(v) =>
                form.setValue("hf_token", v, { shouldDirty: true })
              }
              placeholder={hfMasked ? t("form.api.huggingface_placeholder") : "hf_..."}
              error={errors.hf_token?.message}
              onCopied={() => toast.success(t("form.api.copied"))}
            />
            <Hint>
              {hfMasked
                ? t("form.api.huggingface_current_hint", { masked: hfMasked })
                : t("form.api.huggingface_hint")}
            </Hint>
          </div>
        </div>
      }
    />
  );
}
