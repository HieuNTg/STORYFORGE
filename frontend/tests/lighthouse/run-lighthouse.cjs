// Lighthouse audit runner for Phase 6 cutover gate.
// Runs perf/a11y/best-practices audits on every route (dark theme = default).
// Gate: perf ≥ 90, a11y ≥ 95, best-practices ≥ 90 on all 12 routes.
//
// Light theme is covered by axe (tests/a11y/axe.spec.ts walks both themes).
// Lighthouse a11y rules are a subset of axe-core's, so axe in both themes +
// lighthouse on default theme satisfies the cutover gate without the
// localStorage-injection complexity.

const lighthouse = require("lighthouse").default ?? require("lighthouse");
const chromeLauncher = require("chrome-launcher");
const fs = require("fs");
const path = require("path");

const ROUTES = [
  "/",
  "/library/",
  "/library/demo/",
  "/branching/demo/",
  "/analytics/demo/",
  "/settings/",
  "/providers/",
  "/export/demo/",
  "/account/",
  "/gallery/",
  "/usage/",
  "/guide/",
];

const BASE = "http://localhost:3000";
const GATE = { performance: 90, accessibility: 95, "best-practices": 90 };

async function audit(url, port) {
  const result = await lighthouse(url, {
    logLevel: "error",
    output: "json",
    onlyCategories: ["performance", "accessibility", "best-practices"],
    port,
  });
  return result.lhr;
}

(async () => {
  const chrome = await chromeLauncher.launch({ chromeFlags: ["--headless=new", "--no-sandbox"] });
  const summary = [];
  const failures = [];
  for (const route of ROUTES) {
    const url = `${BASE}${route}`;
    try {
      const lhr = await audit(url, chrome.port);
      const scores = {
        performance: Math.round((lhr.categories.performance.score ?? 0) * 100),
        accessibility: Math.round((lhr.categories.accessibility.score ?? 0) * 100),
        "best-practices": Math.round((lhr.categories["best-practices"].score ?? 0) * 100),
      };
      const passed =
        scores.performance >= GATE.performance &&
        scores.accessibility >= GATE.accessibility &&
        scores["best-practices"] >= GATE["best-practices"];
      const row = { route, ...scores, passed };
      summary.push(row);
      if (!passed) failures.push(row);
      process.stdout.write(
        `${route.padEnd(20)}  perf=${scores.performance}  a11y=${scores.accessibility}  bp=${scores["best-practices"]}  ${passed ? "PASS" : "FAIL"}\n`,
      );
    } catch (e) {
      const row = { route, error: e.message, passed: false };
      summary.push(row);
      failures.push(row);
      process.stdout.write(`${route} ERROR ${e.message}\n`);
    }
  }
  await chrome.kill();
  fs.writeFileSync(path.join(__dirname, "lighthouse-report.json"), JSON.stringify(summary, null, 2));
  process.stdout.write(`\nTotal: ${summary.length}  Failures: ${failures.length}\n`);
  process.exit(failures.length > 0 ? 1 : 0);
})();
