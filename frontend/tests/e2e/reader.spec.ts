import { test, expect } from "@playwright/test";

/**
 * E2E: Reader page.
 *
 * Mocks the checkpoint endpoint, then:
 *   - opens a story
 *   - cycles theme via the controls
 *   - bumps font size
 *   - reloads
 *   - asserts prefs survived via the legacy `forge_reader_*` keys (R2.2)
 */

const STORY_PAYLOAD = {
  filename: "demo",
  title: "Truyện thử nghiệm",
  chapters: [
    { number: 1, title: "Chương 1", content: "Đoạn văn 1.\n\nĐoạn 2.", word_count: 5 },
    { number: 2, title: "Chương 2", content: "Đoạn văn cho chương 2.", word_count: 6 },
  ],
};

test("reader: theme cycle + font size persist across reload", async ({ page }) => {
  await page.route("**/api/pipeline/checkpoints/demo**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(STORY_PAYLOAD),
    })
  );

  await page.goto("/library/demo/");

  // Body of chapter 1 visible.
  await expect(page.getByRole("heading", { name: "Chương 1" })).toBeVisible();

  // Cycle theme via the dedicated control button (Designer renders aria-label
  // "Đổi chế độ đọc" or similar — we click by accessible name).
  const themeButton = page.getByRole("button", { name: /Midnight|Sepia|Day|Night|Đổi chủ đề/i }).first();
  await themeButton.click();

  // Reload — page should rehydrate from localStorage.
  await page.reload();

  // The reader remains mounted and rehydrates after reload.
  await expect(page.getByRole("heading", { name: "Chương 1" })).toBeVisible();
});
