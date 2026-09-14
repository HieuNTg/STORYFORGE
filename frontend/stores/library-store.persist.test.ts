/**
 * Regression tests for library-store persistence failures.
 *
 * zustand's persist middleware writes to localStorage right after the in-memory
 * state has already changed. On QuotaExceededError that write threw, and the
 * throw propagated out of `addStory` into the SSE `onmessage` handler that calls
 * it — killing the stream mid-`done`. Meanwhile the in-memory state said the
 * story was saved, so the UI showed success right up until the next reload,
 * when the entire library was gone.
 *
 * A 50-story shelf of Vietnamese prose passes the ~5 MB budget long before the
 * 50-story cap, so this is the ordinary case, not an edge case.
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  useLibraryStore,
  getLibraryPersistError,
} from "./library-store";
import { storySchema, type Story } from "@/types/story";

function makeStory(id: string): Story {
  // Parse rather than cast so the fixture stays valid as the schema evolves.
  return storySchema.parse({
    id,
    title: `Truyện ${id}`,
    genre: "hiện đại",
    setting: "Hà Nội",
    tone: "trầm",
    description: "mô tả",
    characters: [],
    chapters: [],
    language: "vi",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });
}

function quotaError(): DOMException {
  return new DOMException("exceeded the quota", "QuotaExceededError");
}

describe("library-store persistence failures", () => {
  beforeEach(() => {
    useLibraryStore.setState({
      stories: [],
      selectedId: null,
      persistError: null,
    });
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("does not throw out of addStory when the quota is exceeded", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw quotaError();
    });

    // The throw used to escape into the SSE onmessage handler and kill the run.
    expect(() => useLibraryStore.getState().addStory(makeStory("a"))).not.toThrow();
  });

  it("reports a quota failure synchronously so the caller can skip the success toast", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw quotaError();
    });

    useLibraryStore.getState().addStory(makeStory("a"));

    expect(getLibraryPersistError()).toBe("quota");
  });

  it("distinguishes an unavailable store from a full one", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("storage disabled");
    });

    useLibraryStore.getState().addStory(makeStory("a"));

    expect(getLibraryPersistError()).toBe("unavailable");
  });

  it("clears the error once a write succeeds again", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw quotaError();
    });
    useLibraryStore.getState().addStory(makeStory("a"));
    expect(getLibraryPersistError()).toBe("quota");

    spy.mockRestore();
    useLibraryStore.getState().addStory(makeStory("b"));

    expect(getLibraryPersistError()).toBeNull();
  });

  it("publishes the failure onto the store for subscribers", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw quotaError();
    });

    useLibraryStore.getState().addStory(makeStory("a"));
    await Promise.resolve();

    expect(useLibraryStore.getState().persistError).toBe("quota");
  });

  it("keeps reading working when localStorage getItem throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });

    expect(() => useLibraryStore.getState().addStory(makeStory("a"))).not.toThrow();
  });
});
