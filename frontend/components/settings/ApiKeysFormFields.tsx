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
import { RefreshCw } from "lucide-react";
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
  defaultKey?: string;
  custom?: boolean;
}

// What a card will actually POST. Resolved once per render from the preset,
// the saved profile and whatever the user has typed — so the button, the
// disabled check and the save all read the same values.
interface ProviderCard {
  preset: ProviderPreset;
  name: string;
  baseUrl: string;
  model: string;
  apiKey: string;
  options: Array<{ id: string; label: string }>;
  existing?: ConfigResponse["llm"]["profiles"][number];
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
  // Per-card overrides of the preset's base URL / display name. A preset URL is
  // only a default: users behind a proxy, on a mirror, or running a private
  // OpenAI-compatible server need to point a card somewhere else.
  const [providerUrls, setProviderUrls] = React.useState<Record<string, string>>({});
  const [providerNames, setProviderNames] = React.useState<Record<string, string>>({});
  const [savingProvider, setSavingProvider] = React.useState<string | null>(null);
  // Models a custom endpoint reported on GET {base_url}/models. Keyed by preset
  // name; absent means "never asked", empty array means "asked, got nothing".
  const [fetchedModels, setFetchedModels] = React.useState<
    Record<string, Array<{ id: string; label: string }>>
  >({});
  const [fetchingModels, setFetchingModels] = React.useState<string | null>(null);

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
        defaultKey: p.default_key,
        custom: p.custom,
      })),
    [providerPresetsQuery.data],
  );

  // The key a card is currently holding. Local/dev bridges ship a `defaultKey`
  // (a shared localhost token, not a user secret) so their card is usable
  // without typing; everything else starts empty. Typing always wins — once
  // the user edits the box, `providerKeys` holds the value, even if empty.
  const keyFor = React.useCallback(
    (preset: ProviderPreset) => providerKeys[preset.name] ?? preset.defaultKey ?? "",
    [providerKeys],
  );

  // The model the card's <select> shows. A previously saved profile can hold a
  // model that a preset no longer lists (a provider renamed or retired it), and
  // a <select> whose value matches no <option> renders as blank — so fall back
  // to the preset default instead of showing an empty picker.
  // The models a card offers: whatever the endpoint itself advertised on the
  // last refresh, otherwise the preset's curated list.
  function optionsFor(preset: ProviderPreset) {
    return fetchedModels[preset.name] ?? preset.models;
  }

  // The custom card has no curated dropdown to fall back to — whatever the user
  // typed (or the saved profile holds) is the model, empty included.
  function modelFor(
    preset: ProviderPreset,
    savedModel: string | undefined,
    options: Array<{ id: string; label: string }>,
  ) {
    const chosen = providerModels[preset.name] ?? savedModel ?? preset.model;
    if (preset.custom || options.length === 0) return chosen;
    return options.some((m) => m.id === chosen) ? chosen : preset.model;
  }

  // Ask an endpoint what it can actually run. Every OpenAI-compatible server
  // answers GET {base_url}/models, so a custom provider is usable without the
  // user having to remember the exact model id. Failure is non-fatal — the
  // field stays free text.
  const refreshModels = React.useCallback(
    async (presetName: string, baseUrl: string, apiKey: string, loud: boolean) => {
      if (!baseUrl.trim()) return;
      setFetchingModels(presetName);
      try {
        const res = await apiFetch<{
          models?: Array<{ id: string; label: string }>;
          error?: string;
        }>("/api/config/provider/models", {
          method: "POST",
          body: JSON.stringify({ base_url: baseUrl, api_key: apiKey }),
        });
        // Only replace the curated list when the endpoint actually answered —
        // an empty reply must not turn a working dropdown into a blank one.
        if (res.models?.length) {
          setFetchedModels((prev) => ({ ...prev, [presetName]: res.models! }));
        }
        if (loud && !res.models?.length) {
          toast.error(res.error || t("form.api.fetch_models_empty"));
        }
      } catch (e) {
        if (loud) {
          toast.error(e instanceof Error ? e.message : t("form.api.fetch_models_empty"));
        }
      } finally {
        setFetchingModels(null);
      }
    },
    [t],
  );

  // Cards already auto-refreshed, keyed by (card, url, key). Without this the
  // effect below would re-fire on every render that touches provider state.
  const autoFetched = React.useRef<Set<string>>(new Set());

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

  // Auto-refresh a card's model list once it has somewhere to ask and something
  // to ask with: a saved profile (the server reuses its stored key), a typed
  // key, or — for the custom card — just a URL. Debounced so typing a key or a
  // URL fires one request when it settles, not one per keystroke.
  React.useEffect(() => {
    const timer = setTimeout(() => {
      for (const preset of providerPresets) {
        const name = (providerNames[preset.name] ?? preset.name).trim() || preset.name;
        const existing = profileByName.get(name);
        const url = (
          providerUrls[preset.name] ??
          existing?.base_url ??
          preset.baseUrl
        ).trim();
        if (!/^https?:\/\/\S+$/i.test(url)) continue;
        const key = keyFor(preset).trim();
        if (!preset.custom && !key && !existing?.api_key_masked) continue;
        const signature = `${preset.name}|${url}|${key}`;
        if (autoFetched.current.has(signature)) continue;
        autoFetched.current.add(signature);
        void refreshModels(preset.name, url, key, false);
      }
    }, 700);
    return () => clearTimeout(timer);
  }, [
    providerPresets,
    providerNames,
    providerUrls,
    providerKeys,
    profileByName,
    keyFor,
    refreshModels,
  ]);

  // The card a preset renders as: preset defaults, overridden by the saved
  // profile, overridden by what the user typed.
  function cardFor(preset: ProviderPreset): ProviderCard {
    const name = (providerNames[preset.name] ?? preset.name).trim() || preset.name;
    const existing = profileByName.get(name);
    const options = optionsFor(preset);
    return {
      preset,
      name,
      baseUrl: providerUrls[preset.name] ?? existing?.base_url ?? preset.baseUrl,
      model: modelFor(preset, existing?.model, options),
      apiKey: keyFor(preset),
      options,
      existing,
    };
  }

  async function saveProvider(card: ProviderCard) {
    const { preset } = card;
    const apiKey = card.apiKey.trim();
    if (!apiKey) {
      toast.error(t("form.api.enter_key_first", { provider: preset.label }));
      return;
    }
    const baseUrl = card.baseUrl.trim();
    if (!baseUrl) {
      toast.error(t("form.api.enter_url_first", { provider: preset.label }));
      return;
    }
    if (!card.model.trim()) {
      toast.error(t("form.api.enter_model_first", { provider: preset.label }));
      return;
    }
    setSavingProvider(preset.name);
    try {
      await apiFetch("/api/config/profiles", {
        method: "POST",
        body: JSON.stringify({
          name: card.name,
          base_url: baseUrl,
          api_key: apiKey,
          // Same values the card is showing, so "Add"/"Update" saves exactly
          // what the user is looking at.
          model: card.model.trim(),
          enabled: true,
        }),
      });
      // Drop the typed secret right after a successful save. A local/dev
      // bridge falls back to its (non-secret) prefill so the card stays ready.
      setProviderKeys((prev) => ({
        ...prev,
        [preset.name]: preset.defaultKey ?? "",
      }));
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
              <h3 className="text-sm font-medium text-foreground">
                {t("form.api.quick_provider")}
              </h3>
              <p className="text-xs text-muted-foreground">
                {t("form.api.quick_provider_desc")}
              </p>
            </div>
            {providerPresetsQuery.isLoading && providerPresets.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                {t("form.api.loading_providers")}
              </p>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {providerPresets.map((preset) => {
                const card = cardFor(preset);
                const existing = card.existing;
                const busy = savingProvider === preset.name;
                const incomplete =
                  !card.apiKey.trim() || !card.baseUrl.trim() || !card.model.trim();
                return (
                  <div
                    key={preset.name}
                    className="rounded-md border border-border bg-card/60 p-3"
                  >
                    <div className="mb-2 flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        {preset.custom ? (
                          <Input
                            value={card.name}
                            onChange={(e) =>
                              setProviderNames((prev) => ({
                                ...prev,
                                [preset.name]: e.target.value,
                              }))
                            }
                            className="h-8 text-sm font-medium"
                            aria-label={t("form.api.provider_name_label")}
                            placeholder={t("form.api.provider_name_label")}
                          />
                        ) : (
                          <div className="text-sm font-medium text-foreground">
                            {preset.label}
                          </div>
                        )}
                        {/* Dropdown when we know the model list (curated, or
                            fetched from the endpoint); free text otherwise. */}
                        <div className="mt-1 flex items-center gap-1">
                          {card.options.length === 0 ? (
                            <Input
                              value={card.model}
                              onChange={(e) =>
                                setProviderModels((prev) => ({
                                  ...prev,
                                  [preset.name]: e.target.value,
                                }))
                              }
                              className="h-8 font-mono text-[11px]"
                              aria-label={t("form.api.model_select_label", {
                                provider: preset.label,
                              })}
                              placeholder={t("form.api.model_placeholder")}
                            />
                          ) : (
                            <select
                              value={card.model}
                              onChange={(e) =>
                                setProviderModels((prev) => ({
                                  ...prev,
                                  [preset.name]: e.target.value,
                                }))
                              }
                              className="h-8 w-full max-w-56 rounded-md border border-input bg-background px-2 font-mono text-[11px] text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              aria-label={t("form.api.model_select_label", {
                                provider: preset.label,
                              })}
                            >
                              {/* A saved/typed model the endpoint no longer
                                  lists must still render, or the picker goes
                                  blank and "Update" would silently change it. */}
                              {card.model &&
                              !card.options.some((m) => m.id === card.model) ? (
                                <option value={card.model}>{card.model}</option>
                              ) : null}
                              {!card.model ? (
                                <option value="">
                                  {t("form.api.model_placeholder")}
                                </option>
                              ) : null}
                              {card.options.map((model) => (
                                <option key={model.id} value={model.id}>
                                  {model.label}
                                </option>
                              ))}
                            </select>
                          )}
                          {/* Every card can re-ask its endpoint — a provider
                              that shipped a model this morning shouldn't need
                              a StoryForge release to become selectable. */}
                          <button
                            type="button"
                            onClick={() =>
                              void refreshModels(
                                preset.name,
                                card.baseUrl.trim(),
                                card.apiKey,
                                true,
                              )
                            }
                            disabled={
                              !card.baseUrl.trim() || fetchingModels === preset.name
                            }
                            className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-input text-muted-foreground hover:text-foreground disabled:opacity-50"
                            title={t("form.api.fetch_models")}
                            aria-label={t("form.api.fetch_models")}
                          >
                            <RefreshCw
                              className={
                                fetchingModels === preset.name
                                  ? "h-3.5 w-3.5 animate-spin"
                                  : "h-3.5 w-3.5"
                              }
                            />
                          </button>
                        </div>
                      </div>
                      <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">
                        {existing?.api_key_masked
                          ? t("api.configured")
                          : t("api.missing")}
                      </span>
                    </div>
                    <Input
                      type="password"
                      autoComplete="off"
                      value={card.apiKey}
                      onChange={(e) =>
                        setProviderKeys((prev) => ({
                          ...prev,
                          [preset.name]: e.target.value,
                        }))
                      }
                      placeholder={
                        existing?.api_key_masked
                          ? t("form.api.existing_key_hint", {
                              masked: existing.api_key_masked,
                            })
                          : preset.placeholder
                      }
                    />
                    {/* Editable base URL — a preset's URL is a default, not a
                        constraint (proxies, mirrors, self-hosted endpoints). */}
                    <Input
                      value={card.baseUrl}
                      onChange={(e) =>
                        setProviderUrls((prev) => ({
                          ...prev,
                          [preset.name]: e.target.value,
                        }))
                      }
                      className="mt-2 h-8 font-mono text-[10px]"
                      spellCheck={false}
                      autoComplete="off"
                      aria-label={t("form.api.base_url_label", {
                        provider: preset.label,
                      })}
                      placeholder="https://api.example.com/v1"
                    />
                    <div className="mt-2 flex items-center justify-end gap-2">
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={busy || incomplete}
                        onClick={() => saveProvider(card)}
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
              onChange={(v) => form.setValue("hf_token", v, { shouldDirty: true })}
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
