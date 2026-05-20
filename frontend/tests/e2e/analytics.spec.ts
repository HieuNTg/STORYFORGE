import { test, expect } from "@playwright/test";

/**
 * E2E: Analytics page.
 *
 * Verifies all 4 stat cards render: Tổng số từ, Chất lượng, Sự kiện,
 * Số từ theo chương.
 */

const STORY = {
  filename: "demo",
  title: "Truyện demo",
  word_count: 4400,
  chapters: [
    { number: 1, title: "Chương 1", content: "x".repeat(20), word_count: 2100 },
    { number: 2, title: "Chương 2", content: "y".repeat(20), word_count: 2300 },
  ],
  quality: { overall: 82 },
  analytics: { events: [{ label: "Layer 1 hoàn tất", at: "2025-01-01T00:00:00Z" }] },
};

test("analytics: renders all four cards", async ({ page }) => {
  await page.route("**/api/pipeline/checkpoints/demo**", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify(STORY) })
  );

  await page.goto("/analytics/demo/");

  await expect(page.getByText(/Tổng số từ/i)).toBeVisible();
  await expect(page.getByText(/Chất lượng/i)).toBeVisible();
  await expect(page.getByText(/Sự kiện/i)).toBeVisible();
  await expect(page.getByText(/Số từ theo chương/i)).toBeVisible();
});
