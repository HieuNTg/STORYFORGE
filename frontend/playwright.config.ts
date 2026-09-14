import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  // Includes both e2e specs and a11y specs (tests/a11y/*.spec.ts).
  testDir: "./tests",
  testMatch: ["e2e/**/*.spec.ts", "a11y/**/*.spec.ts"],
  fullyParallel: false,
  retries: 0,
  workers: 1,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: "npm run dev",
    // Follows PLAYWRIGHT_BASE_URL so a dev server already running on another
    // port is reused; `next dev` refuses to start a second instance for the
    // same directory, which otherwise fails the whole run before test one.
    url: process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
