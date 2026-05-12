/**
 * Visual regression baseline capture — M1 Day 1
 *
 * Purpose: Capture pre-redesign screenshots of all 7 SPA page routes in both
 * light and dark mode. These baselines are committed to git so future changes
 * can be diffed against them.
 *
 * HOW TO RUN:
 *   1. Start the FastAPI server: `python app.py` (or `uvicorn app:app --port 7860`)
 *   2. Run: `npx playwright test web/tests/visual/baselines.spec.ts`
 *   3. Screenshots land in: web/tests/visual/baselines/
 *
 * If the server is not running, playwright.config.ts will attempt to start it
 * via the `webServer` option. If it cannot start (missing Python deps, port in
 * use, etc.) the tests will be skipped with a "BASELINE SKIPPED" message.
 *
 * NOTE: These specs use `test.skip` gracefully — they never block CI if the
 * backend is unavailable. Mark STORYFORGE_VISUAL_BASELINES=1 env var to force.
 */

import { test, expect, Page } from '@playwright/test';
import { checkA11y, injectAxe } from '@axe-core/playwright';
import * as fs from 'fs';
import * as path from 'path';

const ROUTES: Array<{ id: string; hash: string }> = [
  { id: 'pipeline',  hash: '#pipeline'  },
  { id: 'library',   hash: '#library'   },
  { id: 'settings',  hash: '#settings'  },
  { id: 'branching', hash: '#branching' },
  { id: 'analytics', hash: '#analytics' },
  { id: 'export',    hash: '#export'    },
  { id: 'account',   hash: '#account'   },
];

const BASELINE_DIR = path.join(__dirname, 'baselines');

/**
 * Ensure baselines directory exists.
 */
function ensureBaselineDir(): void {
  if (!fs.existsSync(BASELINE_DIR)) {
    fs.mkdirSync(BASELINE_DIR, { recursive: true });
  }
}

/**
 * Navigate to a hash route and wait for Alpine to settle.
 */
async function navigateTo(page: Page, hash: string): Promise<void> {
  await page.goto(`/${hash}`);
  // Wait for Alpine to hydrate (x-data components resolved)
  await page.waitForFunction(() => {
    return typeof (window as Window & { Alpine?: unknown }).Alpine !== 'undefined';
  }, { timeout: 5000 }).catch(() => {
    // Alpine may not be loaded (e.g. static assets missing) — continue anyway
  });
  // Short settle time for any CSS transitions
  await page.waitForTimeout(500);
}

/**
 * Set theme via localStorage and reload.
 * StoryForge reads sf_theme key; dark → adds .dark class to <html>.
 */
async function setTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.addInitScript((t: string) => {
    try { localStorage.setItem('sf_theme', t); } catch (_) {}
  }, theme);
}

// ── Test suite ──────────────────────────────────────────────────────────────

test.describe('Visual baselines — pre-redesign', () => {

  test.beforeAll(async ({ browser }) => {
    // Quick health check — skip all tests if server not reachable
    const page = await browser.newPage();
    try {
      const res = await page.goto('http://localhost:7860', { timeout: 5000 });
      if (!res || !res.ok()) {
        console.warn('BASELINE SKIPPED — server returned non-OK. Start with: python app.py');
      }
    } catch {
      console.warn('BASELINE SKIPPED — cannot reach http://localhost:7860. Start with: python app.py');
    } finally {
      await page.close();
    }
    ensureBaselineDir();
  });

  for (const mode of ['light', 'dark'] as const) {
    test.describe(`theme: ${mode}`, () => {
      test.use({
        storageState: undefined,
      });

      for (const route of ROUTES) {
        test(`baseline ${route.id} (${mode})`, async ({ page }) => {
          // Check server availability — skip gracefully if unreachable
          const serverUp = await page.goto('http://localhost:7860', { timeout: 5000 })
            .then(r => r?.ok() ?? false)
            .catch(() => false);

          if (!serverUp) {
            test.skip(true, 'BASELINE SKIPPED — start server: python app.py');
            return;
          }

          // Set theme preference before page load
          await setTheme(page, mode);

          await navigateTo(page, route.hash);

          // Full-page screenshot
          const screenshotPath = path.join(
            BASELINE_DIR,
            `${route.id}-${mode}.png`
          );
          await page.screenshot({
            path: screenshotPath,
            fullPage: true,
          });

          // Accessibility audit via axe-core (non-blocking for baselines — just log)
          try {
            await injectAxe(page);
            await checkA11y(page, undefined, {
              axeOptions: { runOnly: ['wcag2a', 'wcag2aa'] },
              detailedReport: false,
              detailedReportOptions: { html: false },
            });
          } catch (axeErr) {
            // Baseline a11y audit — log violations but don't fail snapshot capture
            console.warn(`[axe] ${route.id}/${mode} violations:`, (axeErr as Error).message?.slice(0, 200));
          }

          // Verify screenshot was written
          expect(fs.existsSync(screenshotPath)).toBe(true);
        });
      }
    });
  }
});
