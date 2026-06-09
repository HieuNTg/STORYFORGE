"use client";

/**
 * library-store — Persisted bookshelf of forged stories.
 *
 * Storage: `storyforge_library_v1` (localStorage, single JSON blob).
 * SSR: `skipHydration: true` + manual `rehydrate()` from a client-only effect.
 * Migrations: v0 → v1 drops legacy state instead of crashing.
 *
 * Hard cap: 50 stories. `addStory` returns `false` when the cap is reached so
 * the caller can surface a toast (see Risk Assessment in phase plan).
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import {
  storySchema,
  storyExportSchema,
  type Story,
  type StoryChapter,
  type StoryExport,
  type ForgeCharacter,
} from "@/types/story";

const STORAGE_KEY = "storyforge_library_v1";
const MAX_STORIES = 50;

interface LibraryState {
  stories: Story[];
  selectedId: string | null;
  hydrated: boolean;

  addStory: (story: Story) => boolean;
  removeStory: (id: string) => void;
  selectStory: (id: string | null) => void;
  updateStory: (id: string, patch: Partial<Story>) => void;
  /**
   * Persist comic panels returned by `POST /api/images/library/generate`.
   * `chapterImages` keys are 1-based chapter numbers (array order); values are
   * `/media/...` URLs written onto `chapters[number-1].images`. Chapters not
   * present in the map keep their existing panels (incremental "Continue" case).
   */
  setStoryChapterImages: (
    storyId: string,
    chapterImages: Record<string | number, string[]>,
  ) => void;
  appendChapter: (storyId: string, chapter: StoryChapter) => void;
  upsertCharacter: (storyId: string, character: ForgeCharacter) => void;
  removeCharacter: (storyId: string, name: string) => void;
  importFromJSON: (payload: unknown) => Story;
  exportToJSON: (id: string) => StoryExport | null;
  clearAll: () => void;
  _markHydrated: () => void;
}

function nowIso(): string {
  return new Date().toISOString();
}

export const useLibraryStore = create<LibraryState>()(
  persist(
    (set, get) => ({
      stories: [],
      selectedId: null,
      hydrated: false,

      addStory: (story) => {
        const parsed = storySchema.parse(story);
        const { stories } = get();
        if (stories.length >= MAX_STORIES) return false;
        if (stories.some((s) => s.id === parsed.id)) {
          set({
            stories: stories.map((s) => (s.id === parsed.id ? parsed : s)),
            selectedId: parsed.id,
          });
          return true;
        }
        set({ stories: [parsed, ...stories], selectedId: parsed.id });
        return true;
      },

      removeStory: (id) => {
        const { stories, selectedId } = get();
        set({
          stories: stories.filter((s) => s.id !== id),
          selectedId: selectedId === id ? null : selectedId,
        });
      },

      selectStory: (id) => set({ selectedId: id }),

      updateStory: (id, patch) => {
        const { stories } = get();
        set({
          stories: stories.map((s) =>
            s.id === id
              ? storySchema.parse({ ...s, ...patch, id: s.id, updatedAt: nowIso() })
              : s,
          ),
        });
      },

      setStoryChapterImages: (storyId, chapterImages) => {
        const { stories } = get();
        set({
          stories: stories.map((s) => {
            if (s.id !== storyId) return s;
            const chapters = s.chapters.map((ch, i) => {
              const next = chapterImages[i + 1] ?? chapterImages[String(i + 1)];
              return next ? { ...ch, images: next } : ch;
            });
            return storySchema.parse({ ...s, chapters, updatedAt: nowIso() });
          }),
        });
      },

      appendChapter: (storyId, chapter) => {
        const { stories } = get();
        set({
          stories: stories.map((s) =>
            s.id === storyId
              ? {
                  ...s,
                  chapters: [...s.chapters, chapter],
                  updatedAt: nowIso(),
                }
              : s,
          ),
        });
      },

      upsertCharacter: (storyId, character) => {
        const { stories } = get();
        set({
          stories: stories.map((s) => {
            if (s.id !== storyId) return s;
            const idx = s.characters.findIndex((c) => c.name === character.name);
            const next =
              idx >= 0
                ? s.characters.map((c, i) => (i === idx ? character : c))
                : [...s.characters, character];
            return { ...s, characters: next, updatedAt: nowIso() };
          }),
        });
      },

      removeCharacter: (storyId, name) => {
        const { stories } = get();
        set({
          stories: stories.map((s) =>
            s.id === storyId
              ? {
                  ...s,
                  characters: s.characters.filter((c) => c.name !== name),
                  updatedAt: nowIso(),
                }
              : s,
          ),
        });
      },

      importFromJSON: (payload) => {
        const parsed: StoryExport = storyExportSchema.parse(payload);
        const { stories } = get();
        if (stories.length >= MAX_STORIES) {
          throw new Error("library_full");
        }
        const incoming = storySchema.parse(parsed.story);
        const exists = stories.some((s) => s.id === incoming.id);
        const story: Story = exists
          ? { ...incoming, id: `${incoming.id}-${Date.now().toString(36)}` }
          : incoming;
        set({ stories: [story, ...stories.filter((s) => s.id !== story.id)] });
        return story;
      },

      exportToJSON: (id) => {
        const story = get().stories.find((s) => s.id === id);
        if (!story) return null;
        return { version: 1, story };
      },

      clearAll: () => set({ stories: [], selectedId: null }),

      _markHydrated: () => set({ hydrated: true }),
    }),
    {
      name: STORAGE_KEY,
      version: 1,
      skipHydration: true,
      partialize: (s) => ({ stories: s.stories, selectedId: s.selectedId }),
      migrate: (persistedState, version) => {
        if (version < 1) {
          return { stories: [], selectedId: null };
        }
        return persistedState as { stories: Story[]; selectedId: string | null };
      },
      onRehydrateStorage: () => (state, error) => {
        if (error) {
          console.warn("[library-store] rehydrate failed, resetting", error);
        }
        state?._markHydrated();
      },
    },
  ),
);

/** Call once from a client-only effect to load persisted state without SSR mismatch. */
export function rehydrateLibrary(): void {
  if (typeof window === "undefined") return;
  void useLibraryStore.persist.rehydrate();
}

export const LIBRARY_MAX_STORIES = MAX_STORIES;
