/* eslint-disable no-console */
/**
 * Playwright a11y spec — walks every Phase 0–4 route in both light and dark
 * mode, injects axe-core, captures violations, and prints a structured per-
 * route summary. Writes JSON to tests/a11y/axe-report.json.
 *
 * Companion to tests/e2e/axe-audit.js (standalone runner — uses a tiny static
 * file server against frontend/out/). This spec hits the dev server defined in
 * playwright.config.ts (defaults to http://localhost:3000) so it can also run
 * against `npm run dev` without a fresh static export. Either one is enough
 * to satisfy the audit; keep both because they exercise different bundles
 * (static export vs. dev).
 *
 * Run:
 *   npx playwright test tests/a11y/axe.spec.ts
 */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

interface AxeNode {
  target: string[];
  failureSummary?: string;
}

interface AxeViolation {
  id: string;
  impact: "minor" | "moderate" | "serious" | "critical" | null;
  help: string;
  helpUrl: string;
  nodes: AxeNode[];
}

interface AxeResult {
  violations: AxeViolation[];
}

interface RouteResult {
  route: string;
  url: string;
  theme: "light" | "dark";
  violations: Array<{
    id: string;
    impact: AxeViolation["impact"];
    help: string;
    helpUrl: string;
    nodes: number;
    targets: string[][];
    messages: Array<string | undefined>;
  }>;
}

const ROUTES: Array<{ id: string; url: string }> = [
  { id: "pipeline", url: "/" },
  { id: "library", url: "/library/" },
  { id: "library-detail", url: "/library/demo/" },
  { id: "branching", url: "/branching/demo/" },
  { id: "analytics", url: "/analytics/demo/" },
  { id: "settings", url: "/settings/" },
  { id: "providers", url: "/providers/" },
  { id: "export", url: "/export/demo/" },
  { id: "account", url: "/account/" },
  { id: "gallery", url: "/gallery/" },
  { id: "usage", url: "/usage/" },
  { id: "guide", url: "/guide/" },
];

const REPORT_PATH = path.join(__dirname, "axe-report.json");
const AXE_SRC = fs.readFileSync(
  path.join(__dirname, "..", "..", "node_modules", "axe-core", "axe.min.js"),
  "utf8",
);

const collected: RouteResult[] = [];

test.afterAll(() => {
  fs.writeFileSync(REPORT_PATH, JSON.stringify(collected, null, 2));
  const total = collected.reduce((s, r) => s + r.violations.length, 0);
  const bySeverity = collected
    .flatMap((r) => r.violations)
    .reduce<Record<string, number>>((acc, v) => {
      const k = v.impact ?? "unknown";
      acc[k] = (acc[k] ?? 0) + 1;
      return acc;
    }, {});
  console.log(
    `\naxe summary — total violations: ${total} ` +
      `(critical: ${bySeverity.critical ?? 0}, ` +
      `serious: ${bySeverity.serious ?? 0}, ` +
      `moderate: ${bySeverity.moderate ?? 0}, ` +
      `minor: ${bySeverity.minor ?? 0})\n` +
      `Report: ${REPORT_PATH}`,
  );
});

for (const theme of ["light", "dark"] as const) {
  for (const route of ROUTES) {
    test(`a11y ${theme}/${route.id}`, async ({ page, context }) => {
      // Mock backend so client queries don't hang in static/dev.
      await page.route("**/api/**", (r) =>
        r.fulfill({
          contentType: "application/json",
          body: JSON.stringify({
            items: [],
            total: 0,
            profiles: [],
            llm: { profiles: [] },
          }),
        }),
      );

      await context.addInitScript((t) => {
        try {
          localStorage.setItem("sf_theme", t);
        } catch {
          /* ignore */
        }
      }, theme);

      await page.goto(route.url, { waitUntil: "networkidle", timeout: 20_000 });

      await page.evaluate((t) => {
        document.documentElement.classList.toggle("dark", t === "dark");
      }, theme);

      await page.addScriptTag({ content: AXE_SRC });

      const axeResult = (await page.evaluate(async () => {
        // @ts-expect-error injected by addScriptTag
        return await axe.run(document, {
          runOnly: {
            type: "tag",
            values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"],
          },
          resultTypes: ["violations"],
        });
      })) as AxeResult;

      collected.push({
        route: route.id,
        url: route.url,
        theme,
        violations: axeResult.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          help: v.help,
          helpUrl: v.helpUrl,
          nodes: v.nodes.length,
          targets: v.nodes.slice(0, 3).map((n) => n.target),
          messages: v.nodes.slice(0, 3).map((n) => n.failureSummary),
        })),
      });

      // Soft assertion: fail only on serious / critical violations. Moderate /
      // minor get logged but don't block — see docs/frontend-accessibility.md
      // for the remediation backlog.
      const blocking = axeResult.violations.filter(
        (v) => v.impact === "critical" || v.impact === "serious",
      );
      expect(
        blocking,
        `${theme}/${route.id} has critical/serious violations:\n` +
          blocking
            .map((v) => `  - ${v.id} (${v.impact}): ${v.help}`)
            .join("\n"),
      ).toHaveLength(0);
    });
  }
}
