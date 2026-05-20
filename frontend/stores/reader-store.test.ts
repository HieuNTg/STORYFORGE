/**
 * reader-store tests — persistence parity with legacy `forge_reader_*` keys.
 *
 * Asserts that:
 *   1. Defaults match the legacy reader (sans, day, normal column, 16px, 1.6).
 *   2. Each setter writes to the exact legacy localStorage key.
 *   3. `hydrate()` reads back legacy keys and patches the store.
 *   4. The legacy `storyforge_reader_font_size` migration shim is honored.
 *   5. Bookmarks roundtrip through `forge_reader_bookmarks`.
 *
 * These assertions are the migration contract per R2.2 — break one and legacy
 * `web/` users lose their reader prefs on cutover.
 */

import { beforeEach, describe, expect, it } from "vitest";
import { useReaderStore } from "./reader-store";

const KEY_FONT_SIZE = "forge_reader_font_size";
const KEY_LINE_HEIGHT = "forge_reader_line_height";
const KEY_FONT_FAMILY = "forge_reader_font_family";
const KEY_THEME = "forge_reader_theme";
const KEY_COLUMN = "forge_reader_column";
const KEY_BOOKMARKS = "forge_reader_bookmarks";
const LEGACY_FONT = "storyforge_reader_font_size";

function resetStore() {
  localStorage.clear();
  useReaderStore.getState().reset();
  // Force re-hydration so subsequent reads pick up cleared localStorage.
  useReaderStore.setState({ _hydrated: false });
}

describe("reader-store", () => {
  beforeEach(() => {
    resetStore();
  });

  it("uses redesign defaults (midnight theme, legacy other fields)", () => {
    const s = useReaderStore.getState();
    expect(s.fontSize).toBe(16);
    expect(s.lineHeight).toBe(1.6);
    expect(s.fontFamily).toBe("sans");
    expect(s.theme).toBe("midnight");
    expect(s.column).toBe("normal");
  });

  it("writes setters to legacy localStorage keys", () => {
    const s = useReaderStore.getState();
    s.setFontSize(20);
    s.setLineHeight(1.8);
    s.setFontFamily("serif");
    s.setTheme("sepia");
    s.setColumn("wide");
    expect(localStorage.getItem(KEY_FONT_SIZE)).toBe("20");
    expect(localStorage.getItem(KEY_LINE_HEIGHT)).toBe("1.8");
    expect(localStorage.getItem(KEY_FONT_FAMILY)).toBe("serif");
    expect(localStorage.getItem(KEY_THEME)).toBe("sepia");
    expect(localStorage.getItem(KEY_COLUMN)).toBe("wide");
  });

  it("cycleTheme advances midnight → sepia → dark → light → midnight", () => {
    const s = useReaderStore.getState();
    s.setTheme("midnight");
    s.cycleTheme();
    expect(useReaderStore.getState().theme).toBe("sepia");
    s.cycleTheme();
    expect(useReaderStore.getState().theme).toBe("dark");
    s.cycleTheme();
    expect(useReaderStore.getState().theme).toBe("light");
    s.cycleTheme();
    expect(useReaderStore.getState().theme).toBe("midnight");
  });

  it("migrates legacy theme tokens day→light and night→dark", () => {
    localStorage.setItem(KEY_THEME, "day");
    useReaderStore.setState({ _hydrated: false });
    useReaderStore.getState().hydrate();
    expect(useReaderStore.getState().theme).toBe("light");
    localStorage.setItem(KEY_THEME, "night");
    useReaderStore.setState({ _hydrated: false });
    useReaderStore.getState().hydrate();
    expect(useReaderStore.getState().theme).toBe("dark");
  });

  it("clamps font size to 12..32", () => {
    const s = useReaderStore.getState();
    s.setFontSize(8);
    expect(useReaderStore.getState().fontSize).toBe(12);
    s.setFontSize(99);
    expect(useReaderStore.getState().fontSize).toBe(32);
  });

  it("hydrate() restores from legacy keys (roundtrip with theme migration)", () => {
    localStorage.setItem(KEY_FONT_SIZE, "22");
    localStorage.setItem(KEY_LINE_HEIGHT, "2.0");
    localStorage.setItem(KEY_FONT_FAMILY, "mono");
    localStorage.setItem(KEY_THEME, "night"); // migrates to "dark"
    localStorage.setItem(KEY_COLUMN, "wide");
    useReaderStore.setState({ _hydrated: false });
    useReaderStore.getState().hydrate();
    const s = useReaderStore.getState();
    expect(s.fontSize).toBe(22);
    expect(s.lineHeight).toBe(2.0);
    expect(s.fontFamily).toBe("mono");
    expect(s.theme).toBe("dark");
    expect(s.column).toBe("wide");
  });

  it("hydrate() honors legacy storyforge_reader_font_size migration", () => {
    localStorage.setItem(LEGACY_FONT, "24");
    useReaderStore.setState({ _hydrated: false });
    useReaderStore.getState().hydrate();
    expect(useReaderStore.getState().fontSize).toBe(24);
  });

  it("saves and clears bookmarks under forge_reader_bookmarks", () => {
    const s = useReaderStore.getState();
    s.saveBookmark("story-1.json", 3, 1200);
    const raw = localStorage.getItem(KEY_BOOKMARKS);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw!) as Record<string, { chapter: number; position?: number }>;
    expect(parsed["story-1.json"].chapter).toBe(3);
    expect(parsed["story-1.json"].position).toBe(1200);

    s.clearBookmark("story-1.json");
    const after = JSON.parse(localStorage.getItem(KEY_BOOKMARKS)!);
    expect(after["story-1.json"]).toBeUndefined();
  });

  it("ignores invalid enum values via migration fallback", () => {
    localStorage.setItem(KEY_THEME, "not-a-theme");
    useReaderStore.setState({ _hydrated: false });
    useReaderStore.getState().hydrate();
    expect(useReaderStore.getState().theme).toBe("midnight");
  });
});
