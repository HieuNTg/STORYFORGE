/**
 * config.ts — zod schemas mirroring the StoryForge backend config payload.
 *
 * Backend source of truth: `config/defaults.py` (LLMConfig + PipelineConfig)
 * and `api/config_routes.py` (GET /api/config response, PUT /api/config body).
 *
 * Two response shapes:
 *   - `configResponseSchema`  — what GET /api/config returns. Reads only the
 *                               fields the UI cares about (masked keys + flags).
 *   - `configUpdateSchema`    — what PUT /api/config accepts (subset; matches
 *                               `ConfigUpdate` Pydantic model in the backend).
 *
 * Form schemas are split per tab:
 *   - generalFormSchema       — language, image_provider, image_prompt_style, primary base_url/model
 *   - apiKeysFormSchema       — api_key, base_url, hf_token (kept in form state only)
 *   - advancedL1FormSchema    — temperature, max_tokens, cheap_model, layer1_model, self-review
 *   - advancedL2FormSchema    — layer2_model + extension hook (currently only model)
 *
 * Strictness: `strict()` rejects unknown keys to catch backend drift early.
 */

import { z } from "zod";

// ---------- GET /api/config response ----------

export const configLlmSchema = z
  .object({
    api_key_masked: z.string(),
    base_url: z.string(),
    model: z.string(),
    temperature: z.number(),
    max_tokens: z.number(),
    cheap_model: z.string(),
    cheap_base_url: z.string(),
    api_keys_masked: z.array(z.string()).default([]),
    api_keys_count: z.number().default(0),
    profiles: z
      .array(
        z.object({
          name: z.string(),
          provider: z.string(),
          base_url: z.string(),
          api_key_masked: z.string(),
          model: z.string(),
          enabled: z.boolean(),
        }),
      )
      .default([]),
    layer1_model: z.string().default(""),
    layer2_model: z.string().default(""),
  })
  .strict();

export const configPipelineSchema = z
  .object({
    language: z.string(),
    enable_self_review: z.boolean(),
    self_review_threshold: z.number(),
    image_provider: z.string(),
    hf_token_masked: z.string(),
    hf_image_model: z.string(),
    image_prompt_style: z.string(),
    enable_simulation_transcript: z.boolean().default(false),
    enable_drama_climax: z.boolean().default(false),
    enable_pipeline_overlay: z.boolean().default(false),
    enable_chapter_illustration: z.boolean().default(false),
  })
  .strict();

export const configResponseSchema = z
  .object({
    llm: configLlmSchema,
    pipeline: configPipelineSchema,
  })
  .strict();

export type ConfigLlm = z.infer<typeof configLlmSchema>;
export type ConfigPipeline = z.infer<typeof configPipelineSchema>;
export type ConfigResponse = z.infer<typeof configResponseSchema>;
export type ConfigProfile = ConfigLlm["profiles"][number];

// ---------- PUT /api/config body ----------

export const configUpdateSchema = z
  .object({
    api_key: z.string().optional(),
    base_url: z.string().optional(),
    model: z.string().optional(),
    temperature: z.number().min(0).max(2).optional(),
    max_tokens: z.number().int().min(1).max(200_000).optional(),
    cheap_model: z.string().optional(),
    cheap_base_url: z.string().optional(),
    language: z.string().optional(),
    layer1_model: z.string().optional(),
    layer2_model: z.string().optional(),
    enable_self_review: z.boolean().optional(),
    self_review_threshold: z.number().min(1).max(5).optional(),
    image_provider: z.string().optional(),
    hf_token: z.string().optional(),
    hf_image_model: z.string().optional(),
    image_prompt_style: z.string().optional(),
  })
  .strict();

export type ConfigUpdate = z.infer<typeof configUpdateSchema>;

// ---------- Per-tab form schemas ----------

export const SUPPORTED_LANGUAGES = ["vi", "en", "zh"] as const;
export const IMAGE_PROVIDERS = [
  "none",
  "dalle",
  "huggingface",
  "seedream",
] as const;

export const generalFormSchema = z.object({
  language: z.enum(SUPPORTED_LANGUAGES),
  image_provider: z.enum(IMAGE_PROVIDERS),
  image_prompt_style: z.string().min(1, "Bắt buộc"),
  base_url: z.string().min(1, "Bắt buộc"),
  model: z.string().min(1, "Bắt buộc"),
});

export type GeneralFormValues = z.infer<typeof generalFormSchema>;

// API keys schema — secrets stay in form state only. Empty string = leave unchanged.
export const apiKeysFormSchema = z.object({
  api_key: z.string(),
  base_url: z.string().min(1, "Bắt buộc"),
  hf_token: z.string(),
});

export type ApiKeysFormValues = z.infer<typeof apiKeysFormSchema>;

export const advancedL1FormSchema = z.object({
  temperature: z.number().min(0).max(2),
  max_tokens: z.number().int().min(256).max(65_536),
  cheap_model: z.string(),
  layer1_model: z.string(),
  enable_self_review: z.boolean(),
  self_review_threshold: z.number().min(1).max(5),
});

export type AdvancedL1FormValues = z.infer<typeof advancedL1FormSchema>;

export const advancedL2FormSchema = z.object({
  layer2_model: z.string(),
});

export type AdvancedL2FormValues = z.infer<typeof advancedL2FormSchema>;

// ---------- Providers ----------

export const providerStatusSchema = z
  .object({
    rate_limit: z
      .object({
        requests_remaining: z.number().nullable().optional(),
        quota_pct: z.number().nullable().optional(),
        reset_at: z.string().nullable().optional(),
      })
      .optional(),
    available_models: z.array(z.string()).optional(),
    last_check: z.string().nullable().optional(),
  })
  .passthrough();

export const allProviderStatusSchema = z.object({
  providers: z.record(z.string(), providerStatusSchema).default({}),
  configured_providers: z.array(z.string()).default([]),
});

export type AllProviderStatus = z.infer<typeof allProviderStatusSchema>;

// ---------- Usage ----------

export const sessionUsageSchema = z
  .object({
    call_count: z.number(),
    total_prompt_tokens: z.number(),
    total_completion_tokens: z.number(),
    total_tokens: z.number(),
    total_cost_usd: z.number(),
  })
  .passthrough();

export type SessionUsage = z.infer<typeof sessionUsageSchema>;
