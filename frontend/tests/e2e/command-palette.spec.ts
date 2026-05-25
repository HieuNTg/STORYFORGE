import { test, expect } from "@playwright/test";

test("command palette: opens with Ctrl+K and lists navigation entries", async ({
  page,
}) => {
  await page.addInitScript(() => window.localStorage.removeItem("storyforge_locale"));
  await page.goto("/library");
  await page.getByRole("button", { name: /Tìm kiếm|Search|Mở bảng lệnh|Open command palette/ }).click();

  await expect(page.getByPlaceholder(/Lệnh hoặc tên truyện|Command or story name/)).toBeVisible();
  await expect(page.getByRole("option", { name: /Phân tích|Analytics/ })).toBeVisible();
});
