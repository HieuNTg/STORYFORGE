import { test, expect } from "@playwright/test";

test("locale switcher: switches shell labels to English", async ({ page, context }) => {
  await context.clearCookies();
  await page.addInitScript(() => window.localStorage.removeItem("storyforge_locale"));
  await page.goto("/library");

  await page.getByRole("button", { name: /Đổi ngôn ngữ|Switch language/ }).click();
  const englishItem = page.getByRole("menuitem", { name: /English/ });
  if (await englishItem.isVisible().catch(() => false)) {
    await englishItem.click();
  }

  await expect(page.getByRole("link", { name: /Library/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Switch language/ })).toBeVisible();
  await expect
    .poll(() => page.evaluate(() => localStorage.getItem("storyforge_locale")))
    .toBe("en");
});
