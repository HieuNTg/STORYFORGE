#!/usr/bin/env node
/**
 * Pre-compress static assets with gzip (level 9) for the FastAPI server's
 * GzippedStaticFiles handler to serve verbatim.
 *
 * Why: at runtime we compress on-demand at level 6 with an LRU cache, which
 * is fine — but level 9 squeezes another ~3-5% out of CSS/JS for the cost of
 * a few hundred ms of build-time CPU, paid once. Production wins.
 *
 * Walks a hard-coded list of asset dirs, writes `<file>.gz` next to every
 * candidate > 1KB when the .gz is missing or older than the source.
 *
 * Run via `npm run build` (wired in package.json after the JS bundle step).
 */

import { promises as fs } from 'node:fs';
import { gzipSync, constants as zlibConstants } from 'node:zlib';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const TARGET_DIRS = [
  'web/css',
  'web/dist/js',
  'web/static',
  'web/js', // built TS output, if present
];

const COMPRESSIBLE_EXTS = new Set(['.css', '.js', '.mjs', '.svg', '.json', '.map', '.html']);
const MIN_SIZE = 1024;

/** Recursively yield files under `dir`. Missing dirs are silently skipped. */
async function* walk(dir) {
  let entries;
  try {
    entries = await fs.readdir(dir, { withFileTypes: true });
  } catch (err) {
    if (err.code === 'ENOENT') return;
    throw err;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
    } else if (entry.isFile()) {
      yield full;
    }
  }
}

async function precompress(filePath) {
  const ext = path.extname(filePath).toLowerCase();
  if (!COMPRESSIBLE_EXTS.has(ext)) return null;
  if (filePath.endsWith('.gz')) return null;

  const srcStat = await fs.stat(filePath);
  if (srcStat.size < MIN_SIZE) return null;

  const gzPath = filePath + '.gz';
  try {
    const gzStat = await fs.stat(gzPath);
    if (gzStat.mtimeMs >= srcStat.mtimeMs) {
      return { filePath, skipped: true, savedBytes: 0 };
    }
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
  }

  const raw = await fs.readFile(filePath);
  const compressed = gzipSync(raw, { level: zlibConstants.Z_BEST_COMPRESSION });
  await fs.writeFile(gzPath, compressed);
  return {
    filePath,
    skipped: false,
    savedBytes: raw.length - compressed.length,
    rawSize: raw.length,
    gzSize: compressed.length,
  };
}

async function main() {
  let compressed = 0;
  let skipped = 0;
  let savedBytes = 0;

  for (const rel of TARGET_DIRS) {
    const abs = path.join(ROOT, rel);
    for await (const file of walk(abs)) {
      const result = await precompress(file);
      if (!result) continue;
      if (result.skipped) {
        skipped += 1;
      } else {
        compressed += 1;
        savedBytes += result.savedBytes;
        const relPath = path.relative(ROOT, result.filePath);
        const pct = ((result.savedBytes / result.rawSize) * 100).toFixed(1);
        console.log(
          `  gz ${relPath}  ${result.rawSize}b → ${result.gzSize}b (-${pct}%)`,
        );
      }
    }
  }

  const savedKb = (savedBytes / 1024).toFixed(1);
  console.log(
    `precompress-static: ${compressed} files compressed, ${skipped} up-to-date, ${savedKb} KB saved`,
  );
}

main().catch((err) => {
  console.error('precompress-static failed:', err);
  process.exit(1);
});
