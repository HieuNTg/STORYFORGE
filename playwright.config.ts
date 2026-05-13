import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright configuration for StoryForge visual regression baselines + e2e smoke specs.
 * See https://playwright.dev/docs/test-configuration
 */
export default defineConfig({
  testDir: './web',
  // Run tests sequentially (visual snapshots are order-dependent)
  fullyParallel: false,
  // Retry on CI to tolerate flakiness
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:7860',
    // Full-page screenshots by default
    screenshot: 'only-on-failure',
    // Record trace on retry
    trace: 'on-first-retry',
  },

  projects: [
    // Visual regression baselines (web/tests/visual/)
    {
      name: 'visual-chromium',
      testDir: './web/tests/visual',
      use: { ...devices['Desktop Chrome'] },
    },
    // E2E smoke specs (web/e2e/) — mocked by default; STORYFORGE_E2E_LIVE=1 for real backend
    {
      name: 'e2e-chromium',
      testDir: './web/e2e',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // FastAPI dev server — start before tests, skip if already running.
  // NOTE: Requires Python environment with all deps installed.
  // If server cannot start, tests will be skipped with a clear message.
  webServer: {
    command: 'python app.py',
    url: 'http://localhost:7860',
    reuseExistingServer: true,
    timeout: 30000,
  },
});
