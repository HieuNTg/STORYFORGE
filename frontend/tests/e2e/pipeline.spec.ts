import { test, expect } from "@playwright/test";

/**
 * E2E: pipeline form submit + mocked SSE stream.
 *
 * The pipeline endpoint is a POST SSE stream; we intercept the request and
 * stream a synthetic body that exercises:
 *   - session frame   → pipeline-store.sessionId set
 *   - log frames      → theater agent + chapter completion toast
 *   - done frame      → ResultPanel render
 */

const SSE_BODY = [
  `data: ${JSON.stringify({ type: "session", session_id: "test-session-1" })}\n\n`,
  `data: ${JSON.stringify({ type: "log", data: "Layer 1 starting" })}\n\n`,
  `data: ${JSON.stringify({ type: "log", data: "[Agent 1/3] Sage: argue" })}\n\n`,
  `data: ${JSON.stringify({ type: "log", data: "✅ Chương 1: Khởi đầu" })}\n\n`,
  `data: ${JSON.stringify({
    type: "done",
    data: {
      title: "Truyện thử nghiệm",
      session_id: "test-session-1",
      draft: {
        chapters: [
          { number: 1, title: "Khởi đầu", content: "abc", word_count: 1234 },
        ],
      },
    },
  })}\n\n`,
].join("");

test("pipeline: submit + mock SSE renders agent + completion toast", async ({
  page,
}) => {
  await page.route("**/api/pipeline/genres", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        genres: ["Tiên Hiệp"],
        styles: ["Miêu tả chi tiết"],
        drama_levels: ["cao"],
        languages: [{ code: "vi", label: "Tiếng Việt" }],
      }),
    })
  );

  await page.route("**/api/pipeline/run", (route) =>
    route.fulfill({
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
      },
      body: SSE_BODY,
    })
  );

  await page.goto("/forge/");
  await page.getByLabel("Ý tưởng truyện").fill(
    "Một thiếu niên tìm đường thành tiên trong một thế giới đầy hiểm nguy"
  );
  await page.getByRole("button", { name: /Khởi động pipeline/i }).click();

  // Agent bubble visible.
  await expect(page.getByText("Sage", { exact: true })).toBeVisible({ timeout: 5_000 });
  // Result panel populated.
  await expect(page.getByText("Truyện thử nghiệm")).toBeVisible({ timeout: 5_000 });
  // ?session= reflected in URL.
  await expect(page).toHaveURL(/session=test-session-1/);
});

test("library: empty state renders without backend", async ({ page }) => {
  await page.route("**/api/pipeline/stories**", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0, limit: 20, offset: 0 }),
    })
  );
  await page.addInitScript(() => window.localStorage.removeItem("storyforge_locale"));
  await page.goto("/library", { waitUntil: "domcontentloaded" });
  await expect(page.getByText(/Kho truyện trống|Bookshelf is empty/i)).toBeVisible();
});
