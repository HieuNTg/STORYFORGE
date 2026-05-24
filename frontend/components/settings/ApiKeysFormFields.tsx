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
import { useUpdateConfig } from "@/lib/api/queries";
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

const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    name: "Google Gemini",
    label: "Gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/",
    model: "gemini-3.5-flash",
    models: [
      { id: "gemini-3.5-flash", label: "Gemini 3.5 Flash" },
      { id: "gemini-3.1-flash-lite", label: "Gemini 3.1 Flash Lite" },
      { id: "gemini-3.1-flash-lite-preview", label: "Gemini 3.1 Flash Lite Preview" },
      { id: "gemini-2.5-pro", label: "Gemini 2.5 Pro" },
      { id: "gemini-2.5-flash", label: "Gemini 2.5 Flash" },
      { id: "gemini-2.0-flash", label: "Gemini 2.0 Flash" },
      { id: "gemma-4-31b-it", label: "Gemma 4 31B" },
      { id: "gemma-4-26b-a4b-it", label: "Gemma 4 26B A4B" },
    ],
    placeholder: "AIza...",
  },
  {
    name: "Anthropic",
    label: "Anthropic",
    baseUrl: "https://api.anthropic.com/v1/",
    model: "claude-sonnet-4-6",
    models: [
      { id: "claude-opus-4-7", label: "Claude Opus 4.7" },
      { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
      { id: "claude-haiku-4-5-20251001", label: "Claude Haiku 4.5" },
      { id: "claude-opus-4-6", label: "Claude Opus 4.6" },
      { id: "claude-sonnet-4-5-20250929", label: "Claude Sonnet 4.5" },
    ],
    placeholder: "sk-ant-...",
  },
  {
    name: "OpenAI",
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5.4-mini",
    models: [
      { id: "gpt-5.5", label: "GPT-5.5" },
      { id: "gpt-5.4-mini", label: "GPT-5.4 Mini" },
      { id: "gpt-5.4-nano", label: "GPT-5.4 Nano" },
      { id: "gpt-chat-latest", label: "GPT Chat Latest" },
      { id: "gpt-4o-mini", label: "GPT-4o Mini" },
      { id: "gpt-4o", label: "GPT-4o" },
    ],
    placeholder: "sk-...",
  },
  {
    name: "OpenRouter",
    label: "OpenRouter Free",
    baseUrl: "https://openrouter.ai/api/v1",
    model: "openrouter/free",
    models: [
      { id: "openrouter/free", label: "Free Models Router" },
      { id: "baidu/cobuddy:free", label: "Baidu CoBuddy (free)" },
      { id: "openrouter/owl-alpha", label: "Owl Alpha" },
      { id: "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", label: "NVIDIA Nemotron 3 Nano Omni (free)" },
      { id: "poolside/laguna-xs.2:free", label: "Poolside Laguna XS.2 (free)" },
      { id: "poolside/laguna-m.1:free", label: "Poolside Laguna M.1 (free)" },
      { id: "deepseek/deepseek-v4-flash:free", label: "DeepSeek V4 Flash (free)" },
      { id: "z-ai/glm-5.1", label: "Z.AI GLM 5.1 (free)" },
      { id: "google/gemma-4-26b-a4b-it:free", label: "Google Gemma 4 26B A4B (free)" },
      { id: "google/gemma-4-31b-it:free", label: "Google Gemma 4 31B (free)" },
      { id: "arcee-ai/trinity-large-thinking:free", label: "Arcee Trinity Large Thinking (free)" },
      { id: "nvidia/nemotron-3-super-120b-a12b:free", label: "NVIDIA Nemotron 3 Super (free)" },
      { id: "minimax/minimax-m2.5:free", label: "MiniMax M2.5 (free)" },
      { id: "qwen/qwen3-next-80b-a3b-instruct:free", label: "Qwen3 Next 80B A3B Instruct (free)" },
      { id: "openai/gpt-oss-120b:free", label: "OpenAI GPT OSS 120B (free)" },
      { id: "openai/gpt-oss-20b:free", label: "OpenAI GPT OSS 20B (free)" },
      { id: "z-ai/glm-4.5-air:free", label: "Z.AI GLM 4.5 Air (free)" },
      { id: "qwen/qwen3-coder:free", label: "Qwen3 Coder 480B A35B (free)" },
      { id: "meta-llama/llama-3.3-70b-instruct:free", label: "Llama 3.3 70B Instruct (free)" },
    ],
    placeholder: "sk-or-...",
  },
  {
    name: "Z.AI",
    label: "Z.AI",
    baseUrl: "https://api.z.ai/api/paas/v4",
    model: "glm-4.7-flash",
    models: [
      { id: "glm-4.7-flash", label: "GLM 4.7 Flash" },
      { id: "glm-4.6", label: "GLM 4.6" },
      { id: "glm-4-flash", label: "GLM 4 Flash" },
    ],
    placeholder: "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.xxxxx",
  },
  {
    name: "Kyma",
    label: "Kyma",
    baseUrl: "https://kymaapi.com/v1",
    model: "qwen-3.6-plus",
    models: [
      { id: "qwen-3.6-plus", label: "Qwen 3.6 Plus" },
      { id: "qwen-3.6", label: "Qwen 3.6" },
      { id: "deepseek-v3.2", label: "DeepSeek V3.2" },
    ],
    placeholder: "ky-...",
  },
];

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
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {PROVIDER_PRESETS.map((preset) => {
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
