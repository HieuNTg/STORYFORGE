import path from "node:path";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const isDev = process.env.NODE_ENV !== "production";

const withNextIntl = createNextIntlPlugin("./lib/i18n/request.ts");

// Static export (`output: 'export'`) is required for prod (FE served by FastAPI).
// But it bails when server code reads `cookies()` (next-intl locale lookup).
// Gate it behind an env flag so `next dev` keeps cookie-based locale switching,
// and CI/prod opts in via `NEXT_OUTPUT_EXPORT=1 npm run build`.
const wantsExport = process.env.NEXT_OUTPUT_EXPORT === "1";

const nextConfig: NextConfig = {
  ...(wantsExport ? { output: "export" as const } : {}),
  trailingSlash: true,
  images: { unoptimized: true },
  turbopack: { root: path.resolve(__dirname) },
  // Disable Next's gzip compression in dev. The dev `rewrites()` proxy below
  // buffers the ENTIRE response body to gzip it whenever the client sends
  // `Accept-Encoding: gzip` — which every browser always does. That buffering
  // defeats SSE: `text/event-stream` frames from `/api/pipeline/run` and
  // `/api/forge/sentence/stream` only flushed to the browser when the stream
  // closed, so the pipeline UI sat frozen ("stuck at Outline") for the whole
  // run and then populated all at once on `done`. The FastAPI backend already
  // excludes `text/event-stream` from its own GZipMiddleware; the proxy was the
  // sole culprit. curl masked it by not sending `Accept-Encoding` by default.
  // Prod is a static export served by FastAPI (no Next server, no proxy), so
  // `compress` has no effect there — gating on dev keeps the switch honest.
  compress: !isDev,
  // Dev-only proxy to the FastAPI backend on :7860.
  // Note: rewrites() is ignored when `output: 'export'` runs at build time;
  // it remains effective for `next dev`.
  async rewrites() {
    if (!isDev) return [];
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:7860/api/:path*",
      },
      // On-disk media (generated portraits, chapter images) is served by the
      // FastAPI `/media` static mount. Without this rewrite an <img src="/media/…">
      // resolves against the Next dev origin (:3001) and 404s, so character
      // avatars and reader reference images never render in dev. In prod the FE
      // is a static export served BY FastAPI (same origin), so no proxy is
      // needed there — this block is dev-only (rewrites() returns [] when !isDev).
      {
        source: "/media/:path*",
        destination: "http://localhost:7860/media/:path*",
      },
    ];
  },
};

export default withNextIntl(nextConfig);
