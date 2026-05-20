"use client";

/**
 * ApiKeysFormFields — RHF body for the "API Keys" settings tab.
 *
 * SECURITY INVARIANTS (do not relax without security review):
 *   1. Secret values live in RHF state ONLY. Never serialized to URL (nuqs),
 *      never written to Zustand persist, never logged.
 *   2. Inputs render as `type="password"` by default. Designer's `MaskedInput`
 *      flips to text on an explicit click — never automatically.
 *   3. PUT payload is delta-only — built from RHF `dirtyFields`. The masked
 *      echo never appears in `dirtyFields` because the user never typed it,
 *      so it cannot be sent back as a "new" key (F4/F5).
 *   4. The masked echo (e.g. `sk-1***abcd`) from GET /api/config is shown as
 *      a hint, never prefilled into the writable input.
 */

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { ApiKeysForm, MaskedInput } from "@/components/settings/ApiKeysForm";
import { Input } from "@/components/ui/input";
import {
  apiKeysFormSchema,
  type ApiKeysFormValues,
  type ConfigResponse,
  type ConfigUpdate,
} from "@/lib/schemas/config";
import { useUpdateConfig } from "@/lib/api/queries";
import { pickDirty } from "@/lib/forms/dirty";

function Hint({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

export interface ApiKeysFormFieldsProps {
  config: ConfigResponse;
}

export function ApiKeysFormFields({ config }: ApiKeysFormFieldsProps) {
  const update = useUpdateConfig();

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
      toast.success("Không có thay đổi để lưu");
      return;
    }

    try {
      await update.mutateAsync(payload);
      // Clear secret fields immediately after a successful save so they
      // don't linger in component state any longer than necessary.
      form.reset({ ...values, api_key: "", hf_token: "" });
      toast.success("Đã lưu khóa API");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Lưu thất bại";
      toast.error(msg);
    }
  });

  const errors = form.formState.errors;
  const apiKeyMasked = config.llm.api_key_masked;
  const hfMasked = config.pipeline.hf_token_masked;

  return (
    <ApiKeysForm
      isSaving={update.isPending}
      onSave={onSave}
      canReset={form.formState.isDirty}
      onReset={() => form.reset(defaults)}
      form={
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <MaskedInput
              label="OpenAI API key"
              value={form.watch("api_key")}
              onChange={(v) =>
                form.setValue("api_key", v, { shouldDirty: true })
              }
              placeholder={apiKeyMasked ? "Để trống nếu không đổi" : "sk-..."}
              error={errors.api_key?.message}
              onCopied={() => toast.success("Đã sao chép khóa")}
            />
            <Hint>
              {apiKeyMasked
                ? `Hiện tại: ${apiKeyMasked} — để trống để giữ nguyên.`
                : "Khóa chưa được cấu hình."}
            </Hint>
          </div>

          <div className="flex flex-col gap-1.5">
            <label
              htmlFor="apikeys-base-url"
              className="text-sm font-medium text-foreground"
            >
              Base URL
            </label>
            <Input
              id="apikeys-base-url"
              autoComplete="off"
              inputMode="url"
              {...form.register("base_url")}
            />
            {errors.base_url ? (
              <p className="text-xs text-destructive">
                {errors.base_url.message}
              </p>
            ) : (
              <Hint>Ví dụ: https://api.openai.com/v1</Hint>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <MaskedInput
              label="HuggingFace token"
              value={form.watch("hf_token")}
              onChange={(v) =>
                form.setValue("hf_token", v, { shouldDirty: true })
              }
              placeholder={hfMasked ? "Để trống nếu không đổi" : "hf_..."}
              error={errors.hf_token?.message}
              onCopied={() => toast.success("Đã sao chép token")}
            />
            <Hint>
              {hfMasked
                ? `Hiện tại: ${hfMasked} — để trống để giữ nguyên.`
                : "Tùy chọn — chỉ cần nếu dùng provider ảnh HuggingFace."}
            </Hint>
          </div>
        </div>
      }
    />
  );
}
