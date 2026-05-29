import { describe, it, expect } from "vitest";
import { clampSessionToTotal } from "./chapter-defaults";

describe("clampSessionToTotal (PR-4 #18 chapter-scope clamp)", () => {
  it("follows the total down when it drops below the session count", () => {
    expect(clampSessionToTotal(5, 3)).toBe(3);
    expect(clampSessionToTotal(60, 10)).toBe(10);
  });

  it("leaves the session count alone when total is >= session", () => {
    expect(clampSessionToTotal(5, 60)).toBe(5);
    expect(clampSessionToTotal(5, 5)).toBe(5);
  });

  it("does not touch the session count for an in-progress / invalid total", () => {
    expect(clampSessionToTotal(5, Number.NaN)).toBe(5);
    expect(clampSessionToTotal(5, 0)).toBe(5);
  });

  it("passes through a non-finite session unchanged", () => {
    expect(Number.isNaN(clampSessionToTotal(Number.NaN, 10))).toBe(true);
  });
});
