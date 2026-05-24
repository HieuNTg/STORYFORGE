"use client";

/**
 * GeneralFormFields — RHF + zod body for the General tab.
 *
 * Designer owns `GeneralForm.tsx` (the Card + sticky Save bar shell). This
 * component is the `form` prop they consume. Keeps Designer's visual contract
 * intact while owning all validation/state.
 */

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslations, useLocale } from "next-intl";
import { toast } from "sonner";

import { GeneralForm } from "@/components/settings/GeneralForm";
import { FlowkitSettings } from "@/components/settings/FlowkitSettings";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  generalFormSchema,
  IMAGE_PROVIDERS,
  SUPPORTED_LANGUAGES,
  type ConfigResponse,
  type GeneralFormValues,
} from "@/lib/schemas/config";
import { useUpdateConfig } from "@/lib/api/queries";
import { pickDirty } from "@/lib/forms/dirty";

function Field({
  label,
  htmlFor,
  error,
  children,
  hint,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium text-foreground">
        {label}
      </label>
      {children}
      {hint && !error ? (
        <p className="text-xs text-muted-foreground">{hint}</p>
      ) : null}
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}

const IMAGE_PROMPT_STYLES = [
  { value: "cinematic", label: "Cinematic" },
  { value: "anime", label: "Anime" },
  { value: "manga", label: "Manga" },
  { value: "webtoon", label: "Webtoon" },
  { value: "realistic", label: "Realistic" },
  { value: "fantasy", label: "Fantasy" },
  { value: "watercolor", label: "Watercolor" },
  { value: "storybook", label: "Storybook" },
] as const;

export interface GeneralFormFieldsProps {
  config: ConfigResponse;
}

export function GeneralFormFields({ config }: GeneralFormFieldsProps) {
  const t = useTranslations("settings_panel");
  const locale = useLocale();
  const update = useUpdateConfig();

  const defaults: GeneralFormValues = React.useMemo(
    () => ({
      language: (SUPPORTED_LANGUAGES as readonly string[]).includes(
        config.pipeline.language,
      )
        ? (config.pipeline.language as GeneralFormValues["language"])
        : ((SUPPORTED_LANGUAGES as readonly string[]).includes(locale)
            ? (locale as GeneralFormValues["language"])
            : "vi"),
      image_provider: (IMAGE_PROVIDERS as readonly string[]).includes(
        config.pipeline.image_provider,
      )
        ? (config.pipeline.image_provider as GeneralFormValues["image_provider"])
        : "none",
      image_prompt_style: config.pipeline.image_prompt_style || "cinematic",
      base_url: config.llm.base_url || "https://api.openai.com/v1",
      model: config.llm.model || "gpt-4o-mini",
    }),
    [config, locale],
  );

  const form = useForm<GeneralFormValues>({
    resolver: zodResolver(generalFormSchema),
    defaultValues: defaults,
  });

  // Keep the form in sync if the underlying config refetches.
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
      toast.success(t("form.general.save_success"));
    } catch (e) {
      const msg = e instanceof Error ? e.message : t("form.save_failed");
      toast.error(msg);
    }
  });

  const errors = form.formState.errors;
  const currentProvider = form.watch("image_provider");

  return (
    <GeneralForm
      isSaving={update.isPending}
      onSave={onSave}
      canReset={form.formState.isDirty}
      onReset={() => form.reset(defaults)}
      form={
        <>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <Field
            label={t("form.general.language")}
            htmlFor="gen-language"
            error={errors.language?.message}
          >
            <Select
              value={form.watch("language")}
              onValueChange={(v) =>
                form.setValue("language", v as GeneralFormValues["language"], {
                  shouldDirty: true,
                })
              }
            >
              <SelectTrigger id="gen-language">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="vi">Tiếng Việt</SelectItem>
                <SelectItem value="en">English</SelectItem>
                <SelectItem value="zh">中文</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field
            label={t("form.general.image_provider")}
            htmlFor="gen-image-provider"
            error={errors.image_provider?.message}
            hint={t("form.general.image_provider_hint")}
          >
            <Select
              value={form.watch("image_provider")}
              onValueChange={(v) =>
                form.setValue(
                  "image_provider",
                  v as GeneralFormValues["image_provider"],
                  { shouldDirty: true },
                )
              }
            >
              <SelectTrigger id="gen-image-provider">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t("form.general.image_provider_none")}</SelectItem>
                <SelectItem value="huggingface">HuggingFace (free)</SelectItem>
                <SelectItem value="dalle">DALL·E</SelectItem>
                <SelectItem value="seedream">Seedream</SelectItem>
                <SelectItem value="flowkit">Flowkit (Google Labs)</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field
            label={t("form.general.image_style")}
            htmlFor="gen-style"
            error={errors.image_prompt_style?.message}
          >
            <Select
              value={form.watch("image_prompt_style") ?? "cinematic"}
              onValueChange={(v) =>
                form.setValue("image_prompt_style", v ?? "cinematic", { shouldDirty: true })
              }
            >
              <SelectTrigger id="gen-style">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {IMAGE_PROMPT_STYLES.map((style) => (
                  <SelectItem key={style.value} value={style.value}>
                    {style.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

        </div>
        {currentProvider === "flowkit" ? (
          <FlowkitSettings config={config} />
        ) : null}
        </>
      }
    />
  );
}
