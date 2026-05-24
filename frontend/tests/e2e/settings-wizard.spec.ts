import { test, expect } from "@playwright/test";

/**
 * E2E: SettingsWizard
 *
 * Opens automatically when GET /api/config returns an empty `api_key_masked`.
 * Once dismissed (close or finish) it must not re-open on subsequent visits.
 */

const EMPTY_CONFIG = {
  llm: {
    api_key_masked: "",
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

test("wizard: auto-opens when api_key is empty; dismiss persists", async ({
  page,
  context,
}) => {
  await context.clearCookies();
  await page.addInitScript(() => {
    if (!window.sessionStorage.getItem("settings-wizard-cleared")) {
      window.localStorage.clear();
      window.sessionStorage.setItem("settings-wizard-cleared", "1");
    }
  });

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
      body: JSON.stringify(EMPTY_CONFIG),
    });
  });

  await page.goto("/settings");

  // Wizard dialog should appear automatically.
  const wizardTitle = page.getByRole("heading", { name: "Chọn nhà cung cấp" });
  await expect(wizardTitle).toBeVisible();

  // Close it (X button → onOpenChange(false) → dismissWizard).
  await page.keyboard.press("Escape");
  await expect(wizardTitle).not.toBeVisible();

  // Reload — wizard should NOT auto-reopen.
  await page.reload();
  await expect(wizardTitle).not.toBeVisible();
});
