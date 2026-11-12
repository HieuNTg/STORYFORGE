import { describe, it, expect, vi, beforeEach } from "vitest";
import * as React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/client";

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => key,
}));

let session = { required: false, valid: true };
const getSession = vi.fn(async () => session);
const openSession = vi.fn();
vi.mock("@/lib/api/session", () => ({
  getSession: () => getSession(),
  openSession: (t: string) => openSession(t),
}));

import { AccessGate } from "./AccessGate";

function renderGate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AccessGate>
        <div>protected-child</div>
      </AccessGate>
    </QueryClientProvider>,
  );
}

describe("AccessGate", () => {
  beforeEach(() => {
    session = { required: false, valid: true };
    getSession.mockClear();
    openSession.mockReset();
  });

  it("renders children when no token is required", async () => {
    session = { required: false, valid: true };
    renderGate();
    expect(await screen.findByText("protected-child")).toBeTruthy();
  });

  it("asks for the token and hides children when required and not valid", async () => {
    session = { required: true, valid: false };
    renderGate();
    expect(await screen.findByLabelText("tokenLabel")).toBeTruthy();
    expect(screen.queryByText("protected-child")).toBeNull();
  });

  it("opens the session and then shows children", async () => {
    session = { required: true, valid: false };
    openSession.mockImplementation(async () => {
      session = { required: true, valid: true };
    });
    renderGate();
    fireEvent.change(await screen.findByLabelText("tokenLabel"), {
      target: { value: "abc" },
    });
    fireEvent.click(screen.getByRole("button", { name: "submit" }));
    expect(await screen.findByText("protected-child")).toBeTruthy();
    expect(openSession).toHaveBeenCalledWith("abc");
  });

  it("shows the invalid message on 401", async () => {
    session = { required: true, valid: false };
    openSession.mockRejectedValue(new ApiError(401, "http_401", "nope"));
    renderGate();
    fireEvent.change(await screen.findByLabelText("tokenLabel"), {
      target: { value: "bad" },
    });
    fireEvent.click(screen.getByRole("button", { name: "submit" }));
    await waitFor(() => expect(screen.getByText("invalid")).toBeTruthy());
    expect(screen.queryByText("protected-child")).toBeNull();
  });

  it("shows a generic error on non-401 failures", async () => {
    session = { required: true, valid: false };
    openSession.mockRejectedValue(new ApiError(500, "http_500", "boom"));
    renderGate();
    fireEvent.change(await screen.findByLabelText("tokenLabel"), {
      target: { value: "abc" },
    });
    fireEvent.click(screen.getByRole("button", { name: "submit" }));
    await waitFor(() => expect(screen.getByText("error")).toBeTruthy());
    expect(screen.queryByText("invalid")).toBeNull();
    expect(screen.queryByText("protected-child")).toBeNull();
  });
});
