/**
 * The Next server (the only thing the browser talks to) must send anti-framing
 * and basic hardening headers on every route; the API's own headers only cover
 * proxied /api and /media responses.
 */
import { describe, it, expect } from "vitest";
import nextConfig from "../next.config";

describe("next.config headers()", () => {
  it("sends frame and hardening headers on all routes", async () => {
    expect(typeof nextConfig.headers).toBe("function");
    const rules = await nextConfig.headers!();
    const all = rules.find((r) => r.source === "/:path*");
    expect(all).toBeDefined();
    const headers = Object.fromEntries(all!.headers.map((h) => [h.key, h.value]));
    expect(headers).toEqual({
      "X-Frame-Options": "DENY",
      "Content-Security-Policy": "frame-ancestors 'none'",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "same-origin",
    });
  });
});
