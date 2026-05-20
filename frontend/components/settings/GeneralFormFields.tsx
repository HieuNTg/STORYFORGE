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
import { toast } from "sonner";

import { GeneralForm } from "@/components/settings/GeneralForm";
import { FlowkitSettings } from "@/components/settings/FlowkitSettings";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
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

export interface GeneralFormFieldsProps {
  config: ConfigResponse;
}

export function GeneralFormFields({ config }: GeneralFormFieldsProps) {
  const update = useUpdateConfig();

  const defaults: GeneralFormValues = React.useMemo(
    () => ({
      language: (SUPPORTED_LANGUAGES as readonly string[]).includes(
        config.pipeline.language,
      )
        ? (config.pipeline.language as GeneralFormValues["language"])
        : "vi",
      image_provider: (IMAGE_PROVIDERS as readonly string[]).includes(
        config.pipeline.image_provider,
      )
        ? (config.pipeline.image_provider as GeneralFormValues["image_provider"])
        : "none",
      image_prompt_style: config.pipeline.image_prompt_style || "cinematic",
      base_url: config.llm.base_url || "https://api.openai.com/v1",
      model: config.llm.model || "gpt-4o-mini",
    }),
    [config],
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
      toast.success("Không có thay đổi để lưu");
      return;
    }
    try {
      await update.mutateAsync(payload);
      toast.success("Đã lưu cài đặt chung");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Lưu thất bại";
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
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field
            label="Ngôn ngữ"
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
            label="Provider hình ảnh"
            htmlFor="gen-image-provider"
            error={errors.image_provider?.message}
            hint="Tắt nếu chưa cần ảnh nhân vật"
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
                <SelectItem value="none">Không sử dụng</SelectItem>
                <SelectItem value="huggingface">HuggingFace (free)</SelectItem>
                <SelectItem value="dalle">DALL·E</SelectItem>
                <SelectItem value="seedream">Seedream</SelectItem>
                <SelectItem value="flowkit">Flowkit (Google Labs)</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field
            label="Phong cách prompt ảnh"
            htmlFor="gen-style"
            error={errors.image_prompt_style?.message}
          >
            <Input
              id="gen-style"
              autoComplete="off"
              {...form.register("image_prompt_style")}
            />
          </Field>

          <Field
            label="Mô hình mặc định"
            htmlFor="gen-model"
            error={errors.model?.message}
          >
            <Input
              id="gen-model"
              autoComplete="off"
              {...form.register("model")}
            />
          </Field>

          <Field
            label="Base URL"
            htmlFor="gen-base-url"
            error={errors.base_url?.message}
            hint="Ví dụ: https://api.openai.com/v1"
          >
            <Input
              id="gen-base-url"
              autoComplete="off"
              inputMode="url"
              className={cn(errors.base_url && "border-destructive")}
              {...form.register("base_url")}
            />
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
