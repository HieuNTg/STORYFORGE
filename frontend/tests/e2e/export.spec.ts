import { test, expect } from "@playwright/test";

/**
 * E2E: /export/demo
 *
 * Verifies the 4 format cards render, selecting PDF opens the config sheet,
 * and clicking download POSTs to the backend export endpoint.
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

  await expect(page.getByText("EPUB")).toBeVisible();
  await expect(page.getByText("PDF")).toBeVisible();
  await expect(page.getByText("HTML")).toBeVisible();
  await expect(page.getByText("Markdown")).toBeVisible();

  // Click the PDF card.
  await page.getByRole("button", { name: /PDF/ }).first().click();

  // The slide-in sheet should open with a download button.
  const download = page.getByRole("button", { name: /Tải xuống/ });
  await expect(download).toBeVisible();
  await download.click();

  // Give the JS-triggered POST a moment.
  await page.waitForTimeout(500);
  expect(exportPosted).toBe(true);
});
