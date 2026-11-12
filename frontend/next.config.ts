import path from "node:path";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./lib/i18n/request.ts");

// Where the FastAPI backend lives. Read at build time and baked into the
// rewrites: `next dev` uses the default, the Docker image is built with
// API_ORIGIN=http://api:7860 (docker/web.Dockerfile).
const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:7860";

const nextConfig: NextConfig = {
  // `node server.js` from .next/standalone is the production server (Docker).
  output: "standalone",
  trailingSlash: true,
  // Serve paths as requested instead of 308-redirecting `/api/x` to `/api/x/`
  // before the rewrite below: the hop re-sends every API POST body, and a
  // client that does not follow redirects (curl, scripts) gets an empty 308.
  // The app's own links already end in "/".
  skipTrailingSlashRedirect: true,
  images: { unoptimized: true },
  turbopack: { root: path.resolve(__dirname) },
  // Never gzip. The rewrites() proxy buffers the whole response body to gzip it
  // whenever the client sends `Accept-Encoding: gzip` (every browser does),
  // which holds back `text/event-stream` frames from `/api/pipeline/run` and
  // `/api/forge/sentence/stream` until the stream closes. FastAPI already
  // compresses its own non-SSE responses.
  compress: false,
  experimental: {
    // The rewrites() proxy drops any upstream request slower than Next's
    // default 30s with a bare `socket hang up`. Test-connection against a slow
    // provider and long SSE pipeline runs legitimately take longer.
    proxyTimeout: 600_000, // 10 minutes
  },
  // The browser only ever talks to this server; /api and /media (generated
  // images) are proxied to the backend.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiOrigin}/api/:path*`,
      },
      {
        source: "/media/:path*",
        destination: `${apiOrigin}/media/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
