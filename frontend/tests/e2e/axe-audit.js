/* eslint-disable no-console */
/**
 * Standalone axe-core audit script.
 *
 * Serves frontend/out/ statically on port 4747, drives Playwright through
 * every Phase 0-4 route in both light and dark theme, injects axe-core from
 * node_modules, and writes a JSON report to tests/e2e/axe-results.json.
 *
 * Run with: node tests/e2e/axe-audit.js
 */
const http = require("http");
const fs = require("fs");
const path = require("path");
const { chromium } = require("@playwright/test");

const ROOT = path.resolve(__dirname, "..", "..");
const OUT = path.join(ROOT, "out");
const AXE_SRC = fs.readFileSync(
  path.join(ROOT, "node_modules", "axe-core", "axe.min.js"),
  "utf8"
);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".json": "application/json; charset=utf-8",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".txt": "text/plain; charset=utf-8",
};

function serve() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let urlPath = req.url.split("?")[0];
      if (urlPath.endsWith("/")) urlPath += "index.html";
      let filePath = path.join(OUT, urlPath);
      if (!fs.existsSync(filePath)) {
        // Try .html fallback for Next static export.
        const htmlPath = filePath + ".html";
        if (fs.existsSync(htmlPath)) filePath = htmlPath;
        else {
          // Try dir/index.html.
          const indexPath = path.join(filePath, "index.html");
          if (fs.existsSync(indexPath)) filePath = indexPath;
        }
      }
      if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
        res.statusCode = 404;
        res.end("not found: " + urlPath);
        return;
      }
      const ext = path.extname(filePath).toLowerCase();
      res.setHeader("content-type", MIME[ext] || "application/octet-stream");
      fs.createReadStream(filePath).pipe(res);
    });
    server.listen(4747, "127.0.0.1", () => resolve(server));
  });
}

const ROUTES = [
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

(async () => {
  const server = await serve();
  console.log("axe-audit: server on http://127.0.0.1:4747");

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const results = [];

  for (const theme of ["light", "dark"]) {
    for (const route of ROUTES) {
      const page = await context.newPage();
      page.on("console", () => {});
      page.on("pageerror", (e) => console.warn(`[${route.id}] pageerror: ${e.message}`));

      // Mock backend so client queries don't hang.
      await page.route("**/api/**", (r) =>
        r.fulfill({
          contentType: "application/json",
          body: JSON.stringify({ items: [], total: 0, profiles: [], llm: { profiles: [] } }),
        })
      );

      // Pre-set theme cookie/localStorage before navigation.
      await context.addInitScript((t) => {
        try { localStorage.setItem("sf_theme", t); } catch (_) {}
      }, theme);

      const url = "http://127.0.0.1:4747" + route.url;
      try {
        await page.goto(url, { waitUntil: "networkidle", timeout: 20_000 });
      } catch (e) {
        results.push({
          route: route.id,
          theme,
          error: "navigation_failed: " + e.message,
          violations: [],
        });
        await page.close();
        continue;
      }

      // Ensure the dark class is applied before scan.
      await page.evaluate((t) => {
        document.documentElement.classList.toggle("dark", t === "dark");
      }, theme);

      // Inject axe-core source.
      await page.addScriptTag({ content: AXE_SRC });

      const axeResult = await page.evaluate(async () => {
        // eslint-disable-next-line no-undef
        return await axe.run(document, {
          runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"] },
          resultTypes: ["violations"],
        });
      });

      results.push({
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
      await page.close();
      console.log(`  ${theme}/${route.id}: ${axeResult.violations.length} violations`);
    }
  }

  await browser.close();
  server.close();

  fs.writeFileSync(
    path.join(__dirname, "axe-results.json"),
    JSON.stringify(results, null, 2)
  );
  console.log("axe-audit: wrote tests/e2e/axe-results.json");
  process.exit(0);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
