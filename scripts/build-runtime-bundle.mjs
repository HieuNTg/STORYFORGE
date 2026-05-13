#!/usr/bin/env node
/**
 * build-runtime-bundle.mjs — concat + minify the 13 runtime <script src> files
 * referenced at the bottom of web/index.html into a single bundle.
 *
 * Sprint perf/forge-shell P2: collapses 13 HTTP requests + parse round-trips
 * into one. The source files use classic-script globals (no ES module syntax),
 * so plain concatenation preserves semantics — they share window scope today
 * and they share it after bundling.
 *
 * Output: web/dist/js/runtime-bundle.min.js  (committed for prod serving)
 * Re-run: npm run build:bundle
 */

import { promises as fs } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { build } from 'esbuild';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// Order MUST match the 13 <script src> tags at the bottom of web/index.html.
// storage-manager + api-client define globals consumed by pages/*; app.js boots
// Alpine after every page function is registered, so it MUST come last.
const SOURCES = [
  'web/js/storage-manager.js',
  'web/js/api-client.js',
  'web/js/pages/library.js',
  'web/js/pages/export.js',
  'web/js/pages/analytics.js',
  'web/js/pages/branching.js',
  'web/js/pages/pipeline.js',
  'web/js/pages/providers.js',
  'web/js/pages/settings.js',
  'web/js/branch-reader.js',
  'web/js/tree-visualizer.js',
  'web/js/i18n.js',
  'web/js/app.js',
];

const OUT_DIR = path.join(ROOT, 'web', 'dist', 'js');
const OUT_FILE = path.join(OUT_DIR, 'runtime-bundle.min.js');

async function main() {
  const missing = [];
  for (const rel of SOURCES) {
    try {
      await fs.access(path.join(ROOT, rel));
    } catch {
      missing.push(rel);
    }
  }
  if (missing.length) {
    console.error('[bundle] missing sources (run `npm run build` first?):\n  ' + missing.join('\n  '));
    process.exit(1);
  }

  const parts = [];
  parts.push('/* runtime-bundle.min.js — concat of ' + SOURCES.length + ' source files (perf/forge-shell P2) */');
  for (const rel of SOURCES) {
    let code = await fs.readFile(path.join(ROOT, rel), 'utf8');
    // tsc emits `export function`/`export const` even with isolatedModules=true; the
    // pre-bundling world treated these as window globals, so strip the `export ` prefix
    // to keep the classic-script semantics under concatenation.
    code = code.replace(/^\s*export\s+(function|const|let|var|class|async\s+function)\s+/gm, '$1 ');
    // Strip any stray ESM marker that would force module mode at runtime.
    code = code.replace(/^Object\.defineProperty\(exports,\s*"__esModule",[^)]*\);?\s*$/gm, '');
    // Drop `import { X, Y } from '...';` lines — concatenation already puts every
    // symbol in shared global scope, and the import binding collides with the
    // `function X` declaration once `export` is stripped from the source module.
    code = code.replace(/^\s*import\s+(?:[\s\S]*?)\s+from\s+['"][^'"]+['"];?\s*$/gm, '');
    code = code.replace(/^\s*import\s+['"][^'"]+['"];?\s*$/gm, '');
    parts.push(`/* === ${rel} === */`);
    parts.push(code);
  }
  const concatenated = parts.join('\n');

  await fs.mkdir(OUT_DIR, { recursive: true });

  const result = await build({
    stdin: { contents: concatenated, loader: 'js', resolveDir: ROOT },
    write: false,
    bundle: false,
    minify: true,
    target: 'es2020',
    // No format: classic-script semantics — every top-level `function name()` stays
    // a window-scoped global so Alpine.data() and inline event handlers can resolve
    // them, exactly as they did before bundling.
    legalComments: 'none',
    logLevel: 'warning',
  });

  const out = result.outputFiles[0].text;
  await fs.writeFile(OUT_FILE, out, 'utf8');

  const sizeRaw = Buffer.byteLength(concatenated, 'utf8');
  const sizeMin = Buffer.byteLength(out, 'utf8');
  console.log(`[bundle] wrote ${path.relative(ROOT, OUT_FILE)}`);
  console.log(`[bundle]   sources: ${SOURCES.length} files`);
  console.log(`[bundle]   raw:     ${sizeRaw.toLocaleString()} bytes`);
  console.log(`[bundle]   minified: ${sizeMin.toLocaleString()} bytes (${((sizeMin / sizeRaw) * 100).toFixed(1)}% of raw)`);
}

main().catch((err) => {
  console.error('[bundle] failed:', err);
  process.exit(1);
});
