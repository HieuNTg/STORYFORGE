/**
 * PipelineForm behaviour tests (PR-4 #18).
 *
 * Two regressions are guarded here:
 *  1. Lowering "tổng số chương" below "chương phiên này" must live-clamp the
 *     per-session count down (not just error on submit).
 *  2. Once the user edits "tổng số chương", switching genre must NOT overwrite
 *     their value with the genre default (the old value-equality heuristic did).
 *
 * Radix Select and the react-query data hooks are mocked so the form renders as
 * plain native controls we can drive with fireEvent.
 */

import { describe, it, expect, vi } from "vitest";
import * as React from "react";
import { render, fireEvent } from "@testing-library/react";

vi.mock("@/lib/api/queries", () => ({
  useGenres: () => ({
    data: {
      genres: ["Tiên Hiệp", "Ngôn Tình"],
      styles: ["Miêu tả chi tiết"],
      languages: [{ code: "vi", label: "Tiếng Việt" }],
    },
  }),
  useConfig: () => ({ data: { pipeline: { image_provider: "none" } } }),
}));

// Render Radix Select primitives as a native <select> so genre changes are
// drivable. SelectItem -> <option>; the trigger/value chrome renders nothing.
vi.mock("@/components/ui/select", () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value: string;
    onValueChange: (v: string) => void;
    children: React.ReactNode;
  }) => (
    <select
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
      data-testid="select"
    >
      {children}
    </select>
  ),
  SelectTrigger: () => null,
  SelectValue: () => null,
  SelectContent: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

import { PipelineForm } from "./PipelineForm";

function setup() {
  const onSubmit = vi.fn();
  const utils = render(<PipelineForm onSubmit={onSubmit} />);
  const total = utils.container.querySelector(
    "#num_chapters"
  ) as HTMLInputElement;
  const session = utils.container.querySelector(
    "#chapters_this_session"
  ) as HTMLInputElement;
  // genre is the first native <select> in the form
  const genre = utils.getAllByTestId("select")[0] as HTMLSelectElement;
  return { onSubmit, total, session, genre, ...utils };
}

describe("PipelineForm #18", () => {
  it("clamps chapters_this_session down when num_chapters is lowered below it", () => {
    const { total, session } = setup();
    // Default session = min(5, 60) = 5, total = 60 (Tiên Hiệp).
    expect(session.value).toBe("5");

    fireEvent.change(total, { target: { value: "3" } });

    expect(session.value).toBe("3");
  });

  it("does not override a user-edited num_chapters when the genre changes", () => {
    const { total, genre } = setup();

    // User deliberately sets a total that happens to equal another genre's
    // default (Ngôn Tình default = 20) to defeat the old equality heuristic.
    fireEvent.change(total, { target: { value: "20" } });
    expect(total.value).toBe("20");

    // Switching genre must leave the user's value intact.
    fireEvent.change(genre, { target: { value: "Ngôn Tình" } });
    expect(total.value).toBe("20");
  });

  it("still bumps num_chapters to the genre default while untouched", () => {
    const { total, genre } = setup();
    expect(total.value).toBe("60"); // Tiên Hiệp default

    fireEvent.change(genre, { target: { value: "Ngôn Tình" } });
    expect(total.value).toBe("20"); // Ngôn Tình default — auto-bump still works
  });
});
