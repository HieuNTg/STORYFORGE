#!/usr/bin/env node
/**
 * build-runtime-bundle.mjs — assemble web/dist/js/runtime-bundle.min.js.
 *
 * Two-stage build:
 *   1. CLASSIC concat — files that publish window-scoped globals consumed by
 *      inline x-data="pipelinePage()" / x-data="libraryPage()" / etc. handlers
 *      in web/index.html. We strip stray `export`/`import` so a top-level
 *      `export function X` becomes a classic `function X` global.
 *   2. ESM IIFE bundle — web/js/app.js as the entry point. esbuild resolves
 *      the full ESM graph (stores/, components/, page exports, d3-force from
 *      node_modules) into one self-contained IIFE. This block owns the
 *      `alpine:init` listener that registers stores and components.
 *
 * Re-run: npm run build:bundle
 */

import { promises as fs } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { build } from 'esbuild';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

// Classic-script sources. Each file's top-level `function name()` (or
// `export function name()` after `export` is stripped) becomes a window
// global so inline x-data="..." handlers resolve. app.js is NOT here — it
// lives in the ESM bundle (stage 2) because its imports require resolution.
const CLASSIC_SOURCES = [
  'web/js/storage-manager.js',
  'web/js/api-client.js',
  'web/js/i18n.js',
  'web/js/pages/library.js',
  'web/js/pages/pipeline.js',
  'web/js/pages/providers.js',
  'web/js/pages/analytics.js',
  'web/js/pages/branching.js',
  'web/js/pages/export.js',
  'web/js/pages/settings.js',
  'web/js/pages/reader.js',
  'web/js/branch-reader.js',
  'web/js/tree-visualizer.js',
];

const ESM_ENTRY = 'web/js/app.js';
const OUT_DIR = path.join(ROOT, 'web', 'dist', 'js');
const OUT_FILE = path.join(OUT_DIR, 'runtime-bundle.min.js');

async function buildClassicBlock() {
  const missing = [];
  for (const rel of CLASSIC_SOURCES) {
    try {
      await fs.access(path.join(ROOT, rel));
    } catch {
      missing.push(rel);
    }
  }
  if (missing.length) {
    throw new Error('missing classic sources:\n  ' + missing.join('\n  '));
  }

  const parts = [];
  parts.push('/* runtime-bundle.min.js — classic concat block */');
  for (const rel of CLASSIC_SOURCES) {
    let code = await fs.readFile(path.join(ROOT, rel), 'utf8');
    code = code.replace(/^\s*export\s+(function|const|let|var|class|async\s+function)\s+/gm, '$1 ');
    code = code.replace(/^\s*export\s*\{[^}]*\}\s*;?\s*$/gm, '');
    code = code.replace(/^Object\.defineProperty\(exports,\s*"__esModule",[^)]*\);?\s*$/gm, '');
    code = code.replace(/^\s*import\s+(?:[\s\S]*?)\s+from\s+['"][^'"]+['"];?\s*$/gm, '');
    code = code.replace(/^\s*import\s+['"][^'"]+['"];?\s*$/gm, '');
    parts.push(`/* === ${rel} === */`);
    parts.push(code);
  }
  const concatenated = parts.join('\n');

  const result = await build({
    stdin: { contents: concatenated, loader: 'js', resolveDir: ROOT },
    write: false,
    bundle: false,
    minify: true,
    target: 'es2020',
    legalComments: 'none',
    logLevel: 'warning',
  });
  return { rawSize: Buffer.byteLength(concatenated, 'utf8'), minified: result.outputFiles[0].text };
}

async function buildEsmBlock() {
  const result = await build({
    entryPoints: [path.join(ROOT, ESM_ENTRY)],
    write: false,
    bundle: true,
    format: 'iife',
    minify: true,
    target: 'es2020',
    platform: 'browser',
    legalComments: 'none',
    logLevel: 'warning',
  });
  return { minified: result.outputFiles[0].text };
}

async function main() {
  const [classicBlock, esmBlock] = await Promise.all([
    buildClassicBlock(),
    buildEsmBlock(),
  ]);

  const out =
    '/* runtime-bundle.min.js — classic globals + ESM IIFE (perf/forge-shell-2 S?) */\n' +
    classicBlock.minified +
    '\n' +
    esmBlock.minified +
    '\n';

  await fs.mkdir(OUT_DIR, { recursive: true });
  await fs.writeFile(OUT_FILE, out, 'utf8');

  const sizeMin = Buffer.byteLength(out, 'utf8');
  console.log(`[bundle] wrote ${path.relative(ROOT, OUT_FILE)}`);
  console.log(`[bundle]   classic raw:     ${classicBlock.rawSize.toLocaleString()} bytes`);
  console.log(`[bundle]   classic min:     ${Buffer.byteLength(classicBlock.minified, 'utf8').toLocaleString()} bytes`);
  console.log(`[bundle]   esm iife min:    ${Buffer.byteLength(esmBlock.minified, 'utf8').toLocaleString()} bytes`);
  console.log(`[bundle]   total:           ${sizeMin.toLocaleString()} bytes`);
}

main().catch((err) => {
  console.error('[bundle] failed:', err);
  process.exit(1);
});
