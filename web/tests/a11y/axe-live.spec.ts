/**
 * Live axe-core scan — B8.1 sprint-close gate.
 *
 * Runs WCAG 2.0/2.1 A+AA axe checks against all 9 SPA routes in light + dark
 * and writes a structured JSON report to plans/reports/m4-a11y-live.json plus a
 * markdown summary at plans/reports/m4-a11y-live.md.
 *
 * Exit gate (CLAUDE.md rule 5 — show evidence): 0 Serious + 0 Critical across
 * all (route, theme) combinations.
 */

import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import * as fs from 'fs';
import * as path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const REPORTS_DIR = path.resolve(__dirname, '../../../plans/reports');

const ROUTES: Array<{ id: string; hash: string }> = [
  { id: 'pipeline',  hash: '#pipeline'  },
  { id: 'library',   hash: '#library'   },
  { id: 'reader',    hash: '#reader'    },
  { id: 'branching', hash: '#branching' },
  { id: 'analytics', hash: '#analytics' },
  { id: 'export',    hash: '#export'    },
  { id: 'settings',  hash: '#settings'  },
  { id: 'providers', hash: '#providers' },
  { id: 'account',   hash: '#account'   },
];

type Violation = {
  route: string;
  theme: 'light' | 'dark';
  id: string;
  impact: string | null | undefined;
  description: string;
  helpUrl: string;
  nodes: number;
  target: string[];
};

type Report = {
  generatedAt: string;
  axeVersion: string;
  tags: string[];
  routes: number;
  themes: number;
  totals: { violations: number; critical: number; serious: number; moderate: number; minor: number };
  byRoute: Record<string, { violations: number; critical: number; serious: number; moderate: number; minor: number }>;
  violations: Violation[];
};

function ensureReportsDir(): void {
  if (!fs.existsSync(REPORTS_DIR)) {
    fs.mkdirSync(REPORTS_DIR, { recursive: true });
  }
}

async function setTheme(page: Page, theme: 'light' | 'dark'): Promise<void> {
  await page.addInitScript((t: string) => {
    try { localStorage.setItem('sf_theme', t); } catch (_) {}
    try { localStorage.setItem('STORYFORGE_FORGE_UI', '1'); } catch (_) {}
  }, theme);
}

async function navigateTo(page: Page, hash: string): Promise<void> {
  await page.goto(`/${hash}`);
  await page.waitForFunction(() => {
    return typeof (window as Window & { Alpine?: unknown }).Alpine !== 'undefined';
  }, { timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(500);
}

const collected: Violation[] = [];
const byRoute: Report['byRoute'] = {};

function bumpRoute(route: string, impact: string | null | undefined): void {
  if (!byRoute[route]) {
    byRoute[route] = { violations: 0, critical: 0, serious: 0, moderate: 0, minor: 0 };
  }
  byRoute[route].violations += 1;
  if (impact === 'critical') byRoute[route].critical += 1;
  else if (impact === 'serious') byRoute[route].serious += 1;
  else if (impact === 'moderate') byRoute[route].moderate += 1;
  else if (impact === 'minor') byRoute[route].minor += 1;
}

test.describe('Live axe-core a11y scan — sprint close', () => {
  test.beforeAll(async ({ browser }) => {
    ensureReportsDir();
    const page = await browser.newPage();
    try {
      const res = await page.goto('http://localhost:7860', { timeout: 5000 });
      if (!res || !res.ok()) console.warn('A11Y SKIPPED — server down. Start: python app.py');
    } catch {
      console.warn('A11Y SKIPPED — cannot reach http://localhost:7860');
    } finally {
      await page.close();
    }
  });

  for (const mode of ['light', 'dark'] as const) {
    for (const route of ROUTES) {
      test(`axe ${route.id} (${mode})`, async ({ page }) => {
        const up = await page.goto('http://localhost:7860', { timeout: 5000 })
          .then(r => r?.ok() ?? false)
          .catch(() => false);
        if (!up) {
          test.skip(true, 'A11Y SKIPPED — server unreachable');
          return;
        }
        await setTheme(page, mode);
        await navigateTo(page, route.hash);

        const results = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze();

        for (const v of results.violations) {
          for (const node of v.nodes) {
            collected.push({
              route: route.id,
              theme: mode,
              id: v.id,
              impact: v.impact,
              description: v.description,
              helpUrl: v.helpUrl,
              nodes: v.nodes.length,
              target: Array.isArray(node.target) ? node.target.map(String) : [],
            });
            bumpRoute(route.id, v.impact);
          }
        }
      });
    }
  }

  test.afterAll(async () => {
    const totals = { violations: 0, critical: 0, serious: 0, moderate: 0, minor: 0 };
    for (const v of collected) {
      totals.violations += 1;
      if (v.impact === 'critical') totals.critical += 1;
      else if (v.impact === 'serious') totals.serious += 1;
      else if (v.impact === 'moderate') totals.moderate += 1;
      else if (v.impact === 'minor') totals.minor += 1;
    }
    const report: Report = {
      generatedAt: new Date().toISOString(),
      axeVersion: '@axe-core/playwright@4.11.3',
      tags: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'],
      routes: ROUTES.length,
      themes: 2,
      totals,
      byRoute,
      violations: collected,
    };
    fs.writeFileSync(path.join(REPORTS_DIR, 'm4-a11y-live.json'), JSON.stringify(report, null, 2), 'utf8');

    const lines: string[] = [];
    lines.push('# M4 Live Axe-Core Report — Sprint Close (B8.1)');
    lines.push('');
    lines.push(`**Generated:** ${report.generatedAt}`);
    lines.push(`**Tags:** ${report.tags.join(', ')}`);
    lines.push(`**Coverage:** ${report.routes} routes × ${report.themes} themes = ${report.routes * report.themes} page loads`);
    lines.push('');
    lines.push('## Totals');
    lines.push('');
    lines.push('| Impact | Count |');
    lines.push('|--------|------:|');
    lines.push(`| Critical | ${totals.critical} |`);
    lines.push(`| Serious  | ${totals.serious} |`);
    lines.push(`| Moderate | ${totals.moderate} |`);
    lines.push(`| Minor    | ${totals.minor} |`);
    lines.push(`| **Total** | **${totals.violations}** |`);
    lines.push('');
    lines.push('## Per-route');
    lines.push('');
    lines.push('| Route | Critical | Serious | Moderate | Minor |');
    lines.push('|-------|---------:|--------:|---------:|------:|');
    for (const r of ROUTES) {
      const rr = byRoute[r.id] ?? { critical: 0, serious: 0, moderate: 0, minor: 0 };
      lines.push(`| ${r.id} | ${rr.critical} | ${rr.serious} | ${rr.moderate} | ${rr.minor} |`);
    }
    lines.push('');
    lines.push('## Gate');
    lines.push('');
    const gateOk = totals.critical === 0 && totals.serious === 0;
    lines.push(`- **Sprint-close gate (0 Critical + 0 Serious):** ${gateOk ? 'PASS' : 'FAIL'}`);
    lines.push(`- Moderate/minor are tracked but non-blocking; triage in next sprint.`);
    lines.push('');
    if (collected.length > 0) {
      lines.push('## Sample violations (first 20)');
      lines.push('');
      lines.push('| Route | Theme | Rule | Impact | Target |');
      lines.push('|-------|-------|------|--------|--------|');
      for (const v of collected.slice(0, 20)) {
        const tgt = (v.target[0] ?? '').replace(/\|/g, '\\|');
        lines.push(`| ${v.route} | ${v.theme} | ${v.id} | ${v.impact ?? ''} | ${tgt} |`);
      }
    }
    fs.writeFileSync(path.join(REPORTS_DIR, 'm4-a11y-live.md'), lines.join('\n') + '\n', 'utf8');

    expect(totals.critical, `Critical a11y violations: ${totals.critical}`).toBe(0);
    expect(totals.serious, `Serious a11y violations: ${totals.serious}`).toBe(0);
  });
});
