"use client";

/**
 * AdvancedL1FormFields — RHF body for the "Advanced L1" settings tab.
 * Composes with Designer's `AdvancedL1Form` shell (Card + sticky Save bar +
 * warning banner). Owns validation + mutation only.
 */

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations } from "next-intl";
import { toast } from "sonner";

import { AdvancedL1Form } from "@/components/settings/AdvancedL1Form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  advancedL1FormSchema,
  type AdvancedL1FormValues,
  type ConfigResponse,
} from "@/lib/schemas/config";
import { useUpdateConfig } from "@/lib/api/queries";
import { pickDirty } from "@/lib/forms/dirty";

const GEMINI_PROFILE_MODELS = [
  { value: "gemini-3.5-flash", label: "Google Gemini · Gemini 3.5 Flash" },
  { value: "gemini-3.1-flash-lite", label: "Google Gemini · Gemini 3.1 Flash Lite" },
  { value: "gemini-3.1-flash-lite-preview", label: "Google Gemini · Gemini 3.1 Flash Lite Preview" },
  { value: "gemini-2.5-pro", label: "Google Gemini · Gemini 2.5 Pro" },
  { value: "gemini-2.5-flash", label: "Google Gemini · Gemini 2.5 Flash" },
  { value: "gemini-2.0-flash", label: "Google Gemini · Gemini 2.0 Flash" },
  { value: "gemma-4-31b-it", label: "Google Gemini · Gemma 4 31B" },
  { value: "gemma-4-26b-a4b-it", label: "Google Gemini · Gemma 4 26B A4B" },
];

function isGeminiProfile(profile: ConfigResponse["llm"]["profiles"][number]) {
  return /gemini|google/i.test(`${profile.name} ${profile.provider} ${profile.base_url}`);
}

export interface AdvancedL1FormFieldsProps {
  config: ConfigResponse;
}

export function AdvancedL1FormFields({ config }: AdvancedL1FormFieldsProps) {
  const t = useTranslations("settings_panel");
  const update = useUpdateConfig();

  const defaults: AdvancedL1FormValues = React.useMemo(
    () => ({
      temperature: config.llm.temperature ?? 0.8,
      max_tokens: config.llm.max_tokens ?? 4096,
      cheap_model: config.llm.cheap_model ?? "",
      layer1_model: config.llm.layer1_model ?? "",
      enable_self_review: config.pipeline.enable_self_review ?? true,
      self_review_threshold: config.pipeline.self_review_threshold ?? 3.0,
    }),
    [config],
  );

  const form = useForm<AdvancedL1FormValues>({
    resolver: zodResolver(advancedL1FormSchema),
    defaultValues: defaults,
  });

  React.useEffect(() => {
    form.reset(defaults);
  }, [defaults, form]);

  const onSave = form.handleSubmit(async (values) => {
    // Delta-only PUT: only send fields the user actually touched (F4/F5).
    const payload = pickDirty(values, form.formState.dirtyFields);
    if (Object.keys(payload).length === 0) {
      toast.success(t("form.no_changes"));
      return;
    }
    try {
      await update.mutateAsync(payload);
      toast.success(t("form.l1.save_success"));
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("form.save_failed");
      toast.error(msg);
    }
  });

  const errors = form.formState.errors;
  const temperature = form.watch("temperature");
  const threshold = form.watch("self_review_threshold");
  const selfReview = form.watch("enable_self_review");
  const cheapModel = form.watch("cheap_model") ?? "";
  const layer1Model = form.watch("layer1_model") ?? "";

  const configuredModels = React.useMemo(() => {
    const options = config.llm.profiles
      .filter((profile) => profile.enabled && profile.model.trim())
      .map((profile) => ({
        value: profile.model,
        label: `${profile.name} · ${profile.model}`,
      }));

    if (config.llm.profiles.some((profile) => profile.enabled && isGeminiProfile(profile))) {
      for (const model of GEMINI_PROFILE_MODELS) {
        if (!options.some((option) => option.value === model.value)) {
          options.push(model);
        }
      }
    }

    for (const value of [cheapModel, layer1Model]) {
      if (value && !options.some((option) => option.value === value)) {
        options.push({ value, label: t("form.l1.current_model", { model: value }) });
      }
    }

    return options;
  }, [cheapModel, config.llm.profiles, layer1Model, t]);

  return (
    <AdvancedL1Form
      isSaving={update.isPending}
      onSave={onSave}
      canReset={form.formState.isDirty}
      onReset={() => form.reset(defaults)}
      form={
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <label
                htmlFor="adv-temp"
                className="text-sm font-medium text-foreground"
              >
                {t("form.l1.temperature")}
              </label>
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {temperature.toFixed(2)}
              </span>
            </div>
            <Slider
              id="adv-temp"
              min={0}
              max={2}
              step={0.05}
              value={[temperature]}
              aria-label={t("form.l1.temperature")}
              onValueChange={(v) => {
                const next = Array.isArray(v) ? v[0] : v;
                form.setValue("temperature", next, { shouldDirty: true });
              }}
            />
            {errors.temperature ? (
              <p className="text-xs text-destructive">
                {errors.temperature.message}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                {t("form.l1.temperature_hint")}
              </p>
            )}
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="adv-max-tokens"
                className="text-sm font-medium text-foreground"
              >
                {t("form.l1.max_tokens")}
              </label>
              <Input
                id="adv-max-tokens"
                type="number"
                min={256}
                max={65_536}
                step={256}
                inputMode="numeric"
                {...form.register("max_tokens", { valueAsNumber: true })}
              />
              {errors.max_tokens ? (
                <p className="text-xs text-destructive">
                  {errors.max_tokens.message}
                </p>
              ) : null}
            </div>

            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="adv-cheap-model"
                className="text-sm font-medium text-foreground"
              >
                {t("form.l1.cheap_model")}
              </label>
              <Select
                value={cheapModel || "__default__"}
                onValueChange={(v) =>
                  form.setValue("cheap_model", v === "__default__" ? "" : (v ?? ""), {
                    shouldDirty: true,
                  })
                }
              >
                <SelectTrigger id="adv-cheap-model" className="w-full">
                  <SelectValue placeholder={t("form.l1.cheap_model_placeholder")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__default__">{t("form.l1.cheap_model_default")}</SelectItem>
                  {configuredModels.map((model) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {t("form.l1.cheap_model_hint")}
              </p>
            </div>

            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <label
                htmlFor="adv-l1-model"
                className="text-sm font-medium text-foreground"
              >
                {t("form.l1.layer1_model")}
              </label>
              <Select
                value={layer1Model || "__default__"}
                onValueChange={(v) =>
                  form.setValue("layer1_model", v === "__default__" ? "" : (v ?? ""), {
                    shouldDirty: true,
                  })
                }
              >
                <SelectTrigger id="adv-l1-model" className="w-full">
                  <SelectValue placeholder={t("form.l1.cheap_model_placeholder")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__default__">{t("form.l1.layer1_model_default")}</SelectItem>
                  {configuredModels.map((model) => (
                    <SelectItem key={model.value} value={model.value}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2">
            <div className="flex flex-col">
              <label
                htmlFor="adv-self-review"
                className="text-sm font-medium text-foreground"
              >
                {t("form.l1.self_review")}
              </label>
              <span className="text-xs text-muted-foreground">
                {t("form.l1.self_review_desc")}
              </span>
            </div>
            <Switch
              id="adv-self-review"
              checked={selfReview}
              onCheckedChange={(v) =>
                form.setValue("enable_self_review", v, { shouldDirty: true })
              }
            />
          </div>

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <label
                htmlFor="adv-self-threshold"
                className="text-sm font-medium text-foreground"
              >
                {t("form.l1.self_review_threshold")}
              </label>
              <span className="font-mono text-xs tabular-nums text-muted-foreground">
                {threshold.toFixed(1)}
              </span>
            </div>
            <Slider
              id="adv-self-threshold"
              min={1}
              max={5}
              step={0.1}
              value={[threshold]}
              aria-label={t("form.l1.self_review_threshold")}
              onValueChange={(v) => {
                const next = Array.isArray(v) ? v[0] : v;
                form.setValue("self_review_threshold", next, {
                  shouldDirty: true,
                });
              }}
              disabled={!selfReview}
            />
            {errors.self_review_threshold ? (
              <p className="text-xs text-destructive">
                {errors.self_review_threshold.message}
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                {t("form.l1.self_review_threshold_hint")}
              </p>
            )}
          </div>
        </div>
      }
    />
  );
}
