import { test, expect } from "@playwright/test";

/**
 * E2E: /export/demo
 *
 * Verifies the export format cards render and clicking PDF POSTs to the
 * backend export endpoint.
 */

test("export: select PDF and trigger download", async ({ page }) => {
  let exportPosted = false;

  await page.route("**/api/export/pdf/demo", async (route) => {
    exportPosted = true;
    await route.fulfill({
      status: 200,
      headers: { "content-type": "application/pdf" },
      body: Buffer.from("%PDF-1.4 mock", "utf-8"),
    });
  });

  await page.goto("/export/?id=demo");

  await expect(page.getByRole("button", { name: /^EPUB/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^PDF/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^HTML/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^ZIP/ })).toBeVisible();

  // Click the PDF card; the current export page downloads directly.
  await page.getByRole("button", { name: /^PDF/ }).click();

  await expect.poll(() => exportPosted).toBe(true);
});
