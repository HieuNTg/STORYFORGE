import { describe, it, expect } from "vitest";
import {
  configResponseSchema,
  configUpdateSchema,
  generalFormSchema,
  advancedL1FormSchema,
  IMAGE_PROVIDERS,
} from "./config";

const VALID_RESPONSE = {
  llm: {
    api_key_masked: "sk-1***abcd",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    temperature: 0.8,
    max_tokens: 4096,
    cheap_model: "",
    cheap_base_url: "",
    api_keys_masked: [],
    api_keys_count: 0,
    profiles: [],
    layer1_model: "",
    layer2_model: "",
  },
  pipeline: {
    language: "vi",
    enable_self_review: true,
    self_review_threshold: 3.0,
    image_provider: "none",
    hf_token_masked: "",
    hf_image_model: "black-forest-labs/FLUX.1-schnell",
    image_prompt_style: "cinematic",
  },
};

describe("qwen-local provider", () => {
  it("is offered as an image provider", () => {
    expect(IMAGE_PROVIDERS).toContain("qwen-local");
    const parsed = generalFormSchema.parse({
      language: "vi",
      image_provider: "qwen-local",
      image_prompt_style: "cinematic",
      base_url: "https://api.openai.com/v1",
      model: "gpt-4o-mini",
    });
    expect(parsed.image_provider).toBe("qwen-local");
  });

  it("defaults the panel fields when the backend omits them", () => {
    const parsed = configResponseSchema.parse(VALID_RESPONSE);
    expect(parsed.pipeline.qwen_local_base_url).toBe("http://localhost:8000/v1");
    expect(parsed.pipeline.qwen_local_use_edit_for_refs).toBe(true);
    expect(parsed.pipeline.qwen_local_size).toBe("");
  });

  it("accepts a qwen-local delta on the update body", () => {
    const parsed = configUpdateSchema.parse({
      qwen_local_base_url: "http://10.0.0.5:8000/v1",
      qwen_local_api_key: "secret",
      qwen_local_size: "16:9",
      qwen_local_use_edit_for_refs: false,
      qwen_local_timeout: 300,
    });
    expect(parsed.qwen_local_size).toBe("16:9");
    expect(parsed.qwen_local_use_edit_for_refs).toBe(false);
  });

  it("rejects a timeout outside the accepted range", () => {
    expect(() => configUpdateSchema.parse({ qwen_local_timeout: 5 })).toThrow();
    expect(() => configUpdateSchema.parse({ qwen_local_timeout: 5000 })).toThrow();
  });

  it("never exposes the raw key on the response schema", () => {
    // The GET surface masks secrets; a strict schema must reject a raw one.
    expect(() =>
      configResponseSchema.parse({
        ...VALID_RESPONSE,
        pipeline: { ...VALID_RESPONSE.pipeline, qwen_local_api_key: "raw" },
      }),
    ).toThrow();
  });
});

describe("configResponseSchema", () => {
  it("accepts a valid masked config payload", () => {
    const parsed = configResponseSchema.parse(VALID_RESPONSE);
    expect(parsed.llm.model).toBe("gpt-4o-mini");
    expect(parsed.pipeline.language).toBe("vi");
  });

  it("rejects unknown keys in llm block (strict)", () => {
    const bad = {
      ...VALID_RESPONSE,
      llm: { ...VALID_RESPONSE.llm, secret_field: "leak" },
    };
    expect(() => configResponseSchema.parse(bad)).toThrow();
  });

  it("rejects missing required fields", () => {
    const bad = { ...VALID_RESPONSE, llm: { ...VALID_RESPONSE.llm } } as Record<
      string,
      unknown
    >;
    delete (bad.llm as Record<string, unknown>).model;
    expect(() => configResponseSchema.parse(bad)).toThrow();
  });
});

describe("configUpdateSchema", () => {
  it("accepts a partial update", () => {
    expect(() =>
      configUpdateSchema.parse({ temperature: 1.2, model: "gpt-4o" }),
    ).not.toThrow();
  });

  it("rejects out-of-range temperature", () => {
    expect(() => configUpdateSchema.parse({ temperature: 5 })).toThrow();
  });

  it("rejects unknown fields", () => {
    expect(() => configUpdateSchema.parse({ malicious: "x" })).toThrow();
  });
});

describe("generalFormSchema", () => {
  it("accepts vi + huggingface", () => {
    expect(() =>
      generalFormSchema.parse({
        language: "vi",
        image_provider: "huggingface",
        image_prompt_style: "cinematic",
        base_url: "https://api.openai.com/v1",
        model: "gpt-4o-mini",
      }),
    ).not.toThrow();
  });

  it("rejects unknown image_provider", () => {
    expect(() =>
      generalFormSchema.parse({
        language: "vi",
        image_provider: "midjourney",
        image_prompt_style: "cinematic",
        base_url: "x",
        model: "y",
      }),
    ).toThrow();
  });
});

describe("advancedL1FormSchema", () => {
  it("accepts valid L1 settings", () => {
    expect(() =>
      advancedL1FormSchema.parse({
        temperature: 0.8,
        max_tokens: 4096,
        cheap_model: "",
        layer1_model: "",
        enable_self_review: true,
        self_review_threshold: 3.0,
        enable_length_gate: true,
        length_gate_min_ratio: 0.85,
      }),
    ).not.toThrow();
  });

  it("rejects a length-gate ratio outside 0.5–1", () => {
    const base = {
      temperature: 0.8,
      max_tokens: 4096,
      cheap_model: "",
      layer1_model: "",
      enable_self_review: true,
      self_review_threshold: 3.0,
      enable_length_gate: true,
    };
    expect(() =>
      advancedL1FormSchema.parse({ ...base, length_gate_min_ratio: 0.2 }),
    ).toThrow();
    expect(() =>
      advancedL1FormSchema.parse({ ...base, length_gate_min_ratio: 1.5 }),
    ).toThrow();
  });

  it("rejects max_tokens above hard cap", () => {
    expect(() =>
      advancedL1FormSchema.parse({
        temperature: 0.8,
        max_tokens: 999_999,
        cheap_model: "",
        layer1_model: "",
        enable_self_review: true,
        self_review_threshold: 3.0,
      }),
    ).toThrow();
  });
});
