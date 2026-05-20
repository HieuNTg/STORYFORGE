import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { FadeIn } from "./FadeIn";

vi.mock("motion/react", () => ({
  motion: {
    div: ({ children, className }: { children: React.ReactNode; className?: string }) => (
      <div data-motion="true" className={className}>
        {children}
      </div>
    ),
  },
  useReducedMotion: () => false,
}));

describe("FadeIn", () => {
  it("renders children", () => {
    const { getByText } = render(<FadeIn>hello</FadeIn>);
    expect(getByText("hello")).toBeTruthy();
  });

  it("passes className through", () => {
    const { container } = render(<FadeIn className="custom">hi</FadeIn>);
    expect(container.firstChild).toHaveProperty("className");
    expect((container.firstChild as HTMLElement).className).toContain("custom");
  });
});
