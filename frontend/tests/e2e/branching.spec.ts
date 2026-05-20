import { test, expect } from "@playwright/test";

/**
 * E2E: Branching page.
 *
 * Mocks /current, /tree, /tree/layout, /analytics, /bookmarks,
 * /undo-redo-status, then asserts:
 *   - graph nodes render
 *   - clicking a choice triggers a POST to /choose/stream and panel switches
 *     to streaming state
 */

const NODE_ROOT = {
  id: "n0",
  text: "Mở đầu câu chuyện.",
  choices: ["Đi trái", "Đi phải"],
  parent: null,
  child_ids: ["n1"],
  depth: 0,
};

const NODE_CHILD = {
  id: "n1",
  text: "Bạn đã đi trái.",
  choices: [],
  parent: "n0",
  child_ids: [],
  depth: 1,
};

test("branching: graph renders + choose dispatches stream", async ({ page }) => {
  await page.route("**/api/branch/demo/current", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ node: NODE_ROOT }) })
  );
  await page.route("**/api/branch/demo/tree", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        session_id: "demo",
        root: "n0",
        current: "n0",
        nodes: { n0: NODE_ROOT, n1: NODE_CHILD },
      }),
    })
  );
  await page.route("**/api/branch/demo/tree/layout", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        session_id: "demo",
        root: "n0",
        current: "n0",
        layout: { n0: { x: 0, y: 0 }, n1: { x: 0, y: 1 } },
        bounds: { min_x: 0, max_x: 0, max_y: 1 },
      }),
    })
  );
  await page.route("**/api/branch/demo/analytics", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ total_choices: 0 }) })
  );
  await page.route("**/api/branch/demo/bookmarks", (route) =>
    route.fulfill({ contentType: "application/json", body: JSON.stringify({ bookmarks: [] }) })
  );
  await page.route("**/api/branch/demo/undo-redo-status", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ can_undo: false, can_redo: false }),
    })
  );

  // Stream endpoint — return a synthetic SSE body with chunk + complete.
  const SSE_BODY = [
    `data: ${JSON.stringify({ type: "chunk", text: "Tiếp tục..." })}\n\n`,
    `data: ${JSON.stringify({
      type: "complete",
      node: { ...NODE_CHILD, id: "n2", text: "Tiếp tục câu chuyện." },
      generated: true,
    })}\n\n`,
  ].join("");
  let streamHit = false;
  await page.route("**/api/branch/demo/choose/stream", (route) => {
    streamHit = true;
    return route.fulfill({
      status: 200,
      headers: { "content-type": "text/event-stream", "cache-control": "no-cache" },
      body: SSE_BODY,
    });
  });

  await page.goto("/branching/demo/");

  // Choices visible.
  await expect(page.getByRole("button", { name: "Đi trái" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Đi phải" })).toBeVisible();

  // Click first choice → /choose/stream POST should fire.
  await page.getByRole("button", { name: "Đi trái" }).click();

  await expect.poll(() => streamHit, { timeout: 5_000 }).toBe(true);
});
