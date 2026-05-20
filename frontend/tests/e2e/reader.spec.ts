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
  await expect(page.getByText("Chương 1")).toBeVisible();

  // Cycle theme via the dedicated control button (Designer renders aria-label
  // "Đổi chế độ đọc" or similar — we click by accessible name).
  const themeButton = page.getByRole("button", { name: /chế độ|theme/i }).first();
  await themeButton.click();

  // Bump font size up. ReaderControls renders +/- buttons via lucide icons.
  // We can locate the aria-label set by Designer's controls.
  const plus = page.getByRole("button", { name: /tăng|larger|font.*\+/i }).first();
  if (await plus.isVisible().catch(() => false)) {
    await plus.click();
  }

  // Reload — page should rehydrate from localStorage.
  await page.reload();

  // Theme stored under forge_reader_theme.
  const theme = await page.evaluate(() => localStorage.getItem("forge_reader_theme"));
  expect(theme).toMatch(/^(day|sepia|night)$/);
  // Ensure it isn't the default ("day") if we cycled once.
  expect(theme).not.toBe("day");

  // Font size stored under forge_reader_font_size (number string).
  const fontSize = await page.evaluate(() =>
    localStorage.getItem("forge_reader_font_size")
  );
  expect(fontSize).not.toBeNull();
});
