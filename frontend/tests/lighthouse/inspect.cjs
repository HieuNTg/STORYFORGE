const j = require("./last-report.json");
const ids = Object.keys(j.audits).filter((k) => /lcp|largest|paint|render-block|bootup|mainthread|unused-/i.test(k));
for (const id of ids) {
  const a = j.audits[id];
  console.log(`${id} | score: ${a.score} | val: ${a.displayValue ?? ""}`);
  if (a.details?.items?.length) {
    console.log(`  items: ${JSON.stringify(a.details.items).slice(0, 800)}`);
  }
}
