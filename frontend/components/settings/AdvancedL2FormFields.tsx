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
import { Input } from "@/components/ui/input";
import {
  advancedL2FormSchema,
  type AdvancedL2FormValues,
  type ConfigResponse,
} from "@/lib/schemas/config";
import { useUpdateConfig } from "@/lib/api/queries";
import { pickDirty } from "@/lib/forms/dirty";

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
            <Input
              id="adv-l2-model"
              autoComplete="off"
              placeholder="để trống để dùng mô hình mặc định"
              {...form.register("layer2_model")}
            />
            <p className="text-xs text-muted-foreground">
              Layer 2 dùng để khuếch đại kịch tính và phân tích nhịp truyện.
            </p>
          </div>
        </div>
      }
    />
  );
}
