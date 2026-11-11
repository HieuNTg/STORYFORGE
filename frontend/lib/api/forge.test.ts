import { beforeEach, describe, expect, it, vi } from "vitest";
import { forgeFromSentenceStream } from "./forge";

type Opts = {
  onopen: (res: { ok: boolean; status: number }) => Promise<void>;
  onmessage: (msg: { event: string; data: string }) => void;
  onclose: () => void;
  onerror: (err: unknown) => void;
};

const state = vi.hoisted(() => ({ captured: null as unknown }));

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn((_url: string, opts: unknown) => {
    state.captured = opts;
    return Promise.resolve();
  }),
}));

const captured = () => state.captured as Opts;

const char = (name: string, role: "protagonist" | "antagonist") => ({
  name,
  role,
  traits: null,
  description: "d",
  backstory: "b",
  secret: "s",
  conflict: "c",
});

const validFinal = {
  title: "T",
  genre: "g",
  setting: "s",
  tone: "t",
  description: "d",
  characters: [char("A", "protagonist"), char("B", "antagonist")],
  firstChapter: {
    title: "Ch1",
    content: "content",
    summary: "sum",
    choices: [
      { id: "a", label: "A", actionPrompt: "do a" },
      { id: "b", label: "B", actionPrompt: "do b" },
    ],
  },
};

const req = { sentenceIdea: "a long enough sentence idea" };

describe("forgeFromSentenceStream", () => {
  beforeEach(() => {
    state.captured = null;
  });

  it("rejects when the stream closes without forge.final", async () => {
    const p = forgeFromSentenceStream(req, {});
    const assertion = expect(p).rejects.toThrow(/closed before completion/);
    expect(() => captured().onclose()).toThrow(/closed before completion/);
    await assertion;
  });

  it("does not retry after settling", async () => {
    const p = forgeFromSentenceStream(req, {});
    captured().onmessage({ event: "forge.final", data: JSON.stringify(validFinal) });
    await expect(p).resolves.toMatchObject({ title: "T" });
    expect(() => captured().onerror(new Error("x"))).toThrow();
  });

  it("rejects on non-ok open and onopen throws", async () => {
    const p = forgeFromSentenceStream(req, {});
    const assertion = expect(p).rejects.toThrow(/HTTP 500/);
    await expect(captured().onopen({ ok: false, status: 500 })).rejects.toThrow(/HTTP 500/);
    await assertion;
  });
});
