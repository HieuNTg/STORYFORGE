// Diagnostic Lighthouse — runs single route, dumps top opportunities/diagnostics.
const lighthouse = require("lighthouse").default ?? require("lighthouse");
const chromeLauncher = require("chrome-launcher");
const fs = require("fs");
const path = require("path");

(async () => {
  const route = process.argv[2] ?? "/library/";
  const url = `http://localhost:3000${route}`;
  const chrome = await chromeLauncher.launch({ chromeFlags: ["--headless=new", "--no-sandbox"] });
  const result = await lighthouse(url, {
    logLevel: "error",
    output: "json",
    onlyCategories: ["performance"],
    port: chrome.port,
    formFactor: "desktop",
    screenEmulation: { mobile: false, disabled: true },
    throttling: {
      rttMs: 40,
      throughputKbps: 10240,
      cpuSlowdownMultiplier: 1,
      requestLatencyMs: 0,
      downloadThroughputKbps: 0,
      uploadThroughputKbps: 0,
    },
  });
  const lhr = result.lhr;
  await chrome.kill();
  fs.writeFileSync(path.join(__dirname, "last-report.json"), JSON.stringify(lhr, null, 2));

  console.log(`\n=== ${route} === perf=${Math.round((lhr.categories.performance.score ?? 0) * 100)}`);

  const want = [
    "first-contentful-paint", "largest-contentful-paint", "total-blocking-time",
    "cumulative-layout-shift", "speed-index", "interactive",
    "lcp-lazy-loaded", "largest-contentful-paint-element",
    "render-blocking-resources", "unused-javascript", "unused-css-rules",
    "uses-text-compression", "uses-long-cache-ttl", "modern-image-formats",
    "uses-optimized-images", "uses-responsive-images", "efficient-animated-content",
    "duplicated-javascript", "legacy-javascript", "third-party-summary",
    "bootup-time", "mainthread-work-breakdown", "dom-size",
    "uses-rel-preconnect", "uses-rel-preload", "font-display",
    "lcp-discovery", "lcp-element", "prioritize-lcp-image", "network-server-latency",
  ];
  for (const id of want) {
    const a = lhr.audits[id];
    if (!a) continue;
    const dv = a.displayValue ?? "";
    const sc = a.score === null ? "n/a" : a.score.toFixed(2);
    console.log(`  [${sc}] ${id.padEnd(38)} ${dv}`);
    if (a.details?.items?.length && (a.numericValue ?? 0) > 100) {
      for (const it of a.details.items.slice(0, 5)) {
        const url = (it.url ?? it.source ?? it.node?.snippet ?? JSON.stringify(it)).toString().slice(0, 120);
        const w = it.wastedBytes ? ` waste=${(it.wastedBytes / 1024).toFixed(0)}KB` : "";
        const m = it.wastedMs ? ` waste=${it.wastedMs.toFixed(0)}ms` : "";
        const s = it.totalBytes ? ` size=${(it.totalBytes / 1024).toFixed(0)}KB` : "";
        const t = it.transferSize ? ` xfer=${(it.transferSize / 1024).toFixed(0)}KB` : "";
        console.log(`         · ${url.replace("http://localhost:3000", "")}${w}${m}${s}${t}`);
      }
    }
  }
})();
