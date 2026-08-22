import { test, expect } from "@playwright/test";

/**
 * E2E: /settings — the Qwen local proxy panel.
 *
 * Covers the three things that can only break in the browser: the panel is
 * gated on the provider selection, the status badge reflects what the probe
 * endpoint says, and Save sends ONLY the fields the user touched — never the
 * masked API key echoed back by GET.
 */

const baseConfig = {
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
    image_provider: "qwen-local",
    hf_token_masked: "",
    hf_image_model: "black-forest-labs/FLUX.1-schnell",
    image_prompt_style: "cinematic",
    qwen_local_base_url: "http://localhost:8000/v1",
    qwen_local_api_key_masked: "change***-key",
    qwen_local_model: "",
    qwen_local_size: "",
    qwen_local_use_edit_for_refs: true,
    qwen_local_timeout: 300,
  },
};

type StatusBody = {
  configured: boolean;
  reachable: boolean;
  qwen_ready: boolean;
  base_url: string;
  error: string;
};

const READY: StatusBody = {
  configured: true,
  reachable: true,
  qwen_ready: true,
  base_url: "http://localhost:8000/v1",
  error: "",
};

const OFFLINE: StatusBody = {
  configured: true,
  reachable: false,
  qwen_ready: false,
  base_url: "http://localhost:8000/v1",
  error: "Connection refused",
};

async function mockSettings(
  page: import("@playwright/test").Page,
  opts: {
    status: StatusBody;
    provider?: string;
    onPut?: (body: Record<string, unknown>) => void;
  },
) {
  await page.route("**/api/config/qwen-local/status", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(opts.status),
    }),
  );
  await page.route("**/api/config", async (route) => {
    if (route.request().method() === "PUT") {
      opts.onPut?.(JSON.parse(route.request().postData() ?? "{}"));
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ status: "ok" }),
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ...baseConfig,
        pipeline: {
          ...baseConfig.pipeline,
          image_provider: opts.provider ?? "qwen-local",
        },
      }),
    });
  });
}

test("qwen-local panel renders with a ready badge when the proxy is up", async ({
  page,
}) => {
  await mockSettings(page, { status: READY });
  await page.goto("/settings");

  const panel = page.getByTestId("qwen-local-settings");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("qwen-local-base-url")).toHaveValue(
    "http://localhost:8000/v1",
  );
  // The stored key is only ever a placeholder — the field itself stays empty.
  await expect(panel.getByTestId("qwen-local-api-key")).toHaveValue("");
  await expect(panel).toContainText("Sẵn sàng");
  // The "no ratio chosen" option must show its translated label, not the
  // internal "auto" sentinel used as the Select's value.
  await expect(panel.getByTestId("qwen-local-size")).toContainText(
    "Theo proxy (1:1)",
  );
});

test("qwen-local panel surfaces the probe error when the proxy is down", async ({
  page,
}) => {
  await mockSettings(page, { status: OFFLINE });
  await page.goto("/settings");

  const panel = page.getByTestId("qwen-local-settings");
  await expect(panel).toContainText("Không kết nối được");
  await expect(panel).toContainText("Connection refused");
});

test("qwen-local panel is not mounted for another provider", async ({ page }) => {
  await mockSettings(page, { status: READY, provider: "none" });
  await page.goto("/settings");

  await expect(page.getByTestId("qwen-local-settings")).toHaveCount(0);
});

test("saving sends only the touched fields, never the masked key", async ({
  page,
}) => {
  const bodies: Record<string, unknown>[] = [];
  await mockSettings(page, { status: READY, onPut: (b) => bodies.push(b) });
  await page.goto("/settings");

  const panel = page.getByTestId("qwen-local-settings");
  await panel.getByTestId("qwen-local-model").fill("qwen3.8-max-image");
  await panel.getByTestId("qwen-local-save").click();

  await expect.poll(() => bodies.length).toBe(1);
  expect(bodies[0]).toEqual({ qwen_local_model: "qwen3.8-max-image" });
  expect(bodies[0].qwen_local_api_key).toBeUndefined();
  expect(bodies[0].qwen_local_api_key_masked).toBeUndefined();
});
