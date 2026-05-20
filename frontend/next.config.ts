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
    ];
  },
};

export default withNextIntl(nextConfig);
