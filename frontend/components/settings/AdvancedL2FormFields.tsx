"use client";

/**
 * AdvancedL2FormFields — RHF body for the "Advanced L2" settings tab.
 *
 * Phase-03 scope: only the L2 model routing override. Future L2 flags
 * (drama ceiling, voice preservation, contract gate, etc.) plug in here.
 */

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { AdvancedL2Form } from "@/components/settings/AdvancedL2Form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  advancedL2FormSchema,
  type AdvancedL2FormValues,
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

export interface AdvancedL2FormFieldsProps {
  config: ConfigResponse;
}

export function AdvancedL2FormFields({ config }: AdvancedL2FormFieldsProps) {
  const update = useUpdateConfig();

  const defaults: AdvancedL2FormValues = React.useMemo(
    () => ({
      layer2_model: config.llm.layer2_model ?? "",
    }),
    [config],
  );

  const form = useForm<AdvancedL2FormValues>({
    resolver: zodResolver(advancedL2FormSchema),
    defaultValues: defaults,
  });

  React.useEffect(() => {
    form.reset(defaults);
  }, [defaults, form]);

  const layer2Model = form.watch("layer2_model");
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

    if (layer2Model && !options.some((option) => option.value === layer2Model)) {
      options.push({ value: layer2Model, label: `Hiện tại · ${layer2Model}` });
    }

    return options;
  }, [config.llm.profiles, layer2Model]);

  const onSave = form.handleSubmit(async (values) => {
    // Delta-only PUT: only send fields the user actually touched (F4/F5).
    const payload = pickDirty(values, form.formState.dirtyFields);
    if (Object.keys(payload).length === 0) {
      toast.success("Không có thay đổi để lưu");
      return;
    }
    try {
      await update.mutateAsync(payload);
      toast.success("Đã lưu cài đặt Layer 2");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Lưu thất bại";
      toast.error(msg);
    }
  });

  return (
    <AdvancedL2Form
      isSaving={update.isPending}
      onSave={onSave}
      canReset={form.formState.isDirty}
      onReset={() => form.reset(defaults)}
      form={
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="adv-l2-model"
              className="text-sm font-medium text-foreground"
            >
              Mô hình Layer 2
            </label>
            <Select
              value={layer2Model || "__default__"}
              onValueChange={(v) =>
                form.setValue("layer2_model", v === "__default__" ? "" : v, {
                  shouldDirty: true,
                })
              }
            >
              <SelectTrigger id="adv-l2-model" className="w-full">
                <SelectValue placeholder="Chọn model đã cấu hình" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__default__">Dùng model mặc định</SelectItem>
                {configuredModels.map((model) => (
                  <SelectItem key={model.value} value={model.value}>
                    {model.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Layer 2 dùng để khuếch đại kịch tính và phân tích nhịp truyện.
            </p>
          </div>
        </div>
      }
    />
  );
}
