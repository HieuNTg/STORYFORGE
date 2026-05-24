import { test, expect } from "@playwright/test";

test("command palette: opens with Ctrl+K and lists navigation entries", async ({
  page,
}) => {
  await page.goto("/library");
  await page.getByRole("button", { name: /Tìm kiếm|Mở bảng lệnh/ }).click();

  await expect(page.getByPlaceholder("Lệnh hoặc tên truyện...")).toBeVisible();
  await expect(page.getByRole("option", { name: /Phân tích/ })).toBeVisible();
});
