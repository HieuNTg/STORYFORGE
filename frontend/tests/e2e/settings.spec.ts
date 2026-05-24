import { test, expect } from "@playwright/test";

/**
 * E2E: /settings — load config, edit a General field, save, reload.
 *
 * The PUT mock asserts that the request body contains ONLY user-changed
 * fields (no masked secrets echoed back). The second GET returns the
 * updated language so we can verify the page reflects the persisted value.
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
    image_provider: "none",
    hf_token_masked: "",
    hf_image_model: "black-forest-labs/FLUX.1-schnell",
    image_prompt_style: "cinematic",
  },
};

test("settings: edit language and save round-trips through PUT /api/config", async ({
  page,
}) => {
  let currentLang = "vi";

  await page.route("**/api/config", async (route) => {
    if (route.request().method() === "PUT") {
      const body = JSON.parse(route.request().postData() ?? "{}");
      // Body must NOT include masked echoes — only user-typed fields.
      expect(body.api_key).toBeUndefined();
      expect(body.hf_token).toBeUndefined();
      if (typeof body.language === "string") currentLang = body.language;
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
        pipeline: { ...baseConfig.pipeline, language: currentLang },
      }),
    });
  });

  await page.goto("/settings");
  // Wait for the General tab content to mount.
  await expect(page.getByText("Phong cách prompt ảnh")).toBeVisible();

  // Switch language to English via the native select trigger.
  await page.getByRole("combobox").first().click();
  await page.getByRole("option", { name: "English" }).click();

  await page.getByRole("button", { name: "Lưu" }).first().click();
  await expect(page.getByText("Đã lưu cài đặt chung")).toBeVisible();

  // Reload and verify the persisted value comes back.
  await page.reload();
  await expect(page.getByRole("combobox").first()).toContainText(/English|en/);
});

test("settings: no api_key value leaks into URL or local storage", async ({
  page,
}) => {
  await page.route("**/api/config", async (route) => {
    if (route.request().method() === "PUT") {
      await route.fulfill({
        contentType: "application/json",
        body: JSON.stringify({ status: "ok" }),
      });
      return;
    }
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(baseConfig),
    });
  });

  await page.goto("/settings");

  // Switch to API Keys tab.
  await page.getByRole("tab", { name: "Khóa API" }).click();

  const secret = "sk-test-FAKE-DO-NOT-USE-canary-leak";
  const apiKeyInput = page.locator('input[type="password"]').first();
  await apiKeyInput.fill(secret);

  // URL must never contain the secret value.
  expect(page.url()).not.toContain(secret);

  // localStorage must never contain the secret value.
  const ls = await page.evaluate(() => JSON.stringify(localStorage));
  expect(ls).not.toContain(secret);
});
