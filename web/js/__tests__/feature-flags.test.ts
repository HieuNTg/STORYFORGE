/**
 * Tests for feature-flags.ts
 *
 * Covers:
 *   - Default: returns false when no flags set
 *   - localStorage override: returns true when sf_forge_ui === '1'
 *   - localStorage override: returns false when sf_forge_ui === '0'
 *   - window global takes priority over localStorage
 *   - setForgeUiOverride: sets, clears localStorage key
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { isForgeUiEnabled, setForgeUiOverride } from '../feature-flags';

describe('isForgeUiEnabled', () => {
  beforeEach(() => {
    // Clean slate for each test
    localStorage.clear();
    // Remove window flag if set by previous test
    if (window.__STORYFORGE_FLAGS__ !== undefined) {
      delete window.__STORYFORGE_FLAGS__;
    }
  });

  it('returns false by default (no localStorage, no window flag)', () => {
    expect(isForgeUiEnabled()).toBe(false);
  });

  it('returns true when localStorage sf_forge_ui === "1"', () => {
    localStorage.setItem('sf_forge_ui', '1');
    expect(isForgeUiEnabled()).toBe(true);
  });

  it('returns false when localStorage sf_forge_ui === "0"', () => {
    localStorage.setItem('sf_forge_ui', '0');
    expect(isForgeUiEnabled()).toBe(false);
  });

  it('returns false when localStorage sf_forge_ui is an unrecognized value', () => {
    localStorage.setItem('sf_forge_ui', 'true'); // not '1'
    expect(isForgeUiEnabled()).toBe(false);
  });

  it('window.__STORYFORGE_FLAGS__.forgeUi = true takes priority over localStorage = "0"', () => {
    localStorage.setItem('sf_forge_ui', '0');
    window.__STORYFORGE_FLAGS__ = { forgeUi: true };
    expect(isForgeUiEnabled()).toBe(true);
  });

  it('window.__STORYFORGE_FLAGS__.forgeUi = false overrides localStorage = "1"', () => {
    localStorage.setItem('sf_forge_ui', '1');
    window.__STORYFORGE_FLAGS__ = { forgeUi: false };
    expect(isForgeUiEnabled()).toBe(false);
  });
});

describe('setForgeUiOverride', () => {
  beforeEach(() => {
    localStorage.clear();
    if (window.__STORYFORGE_FLAGS__ !== undefined) {
      delete window.__STORYFORGE_FLAGS__;
    }
  });

  it('setForgeUiOverride(true) sets sf_forge_ui to "1"', () => {
    setForgeUiOverride(true);
    expect(localStorage.getItem('sf_forge_ui')).toBe('1');
  });

  it('setForgeUiOverride(false) sets sf_forge_ui to "0"', () => {
    setForgeUiOverride(false);
    expect(localStorage.getItem('sf_forge_ui')).toBe('0');
  });

  it('setForgeUiOverride(null) removes sf_forge_ui from localStorage', () => {
    localStorage.setItem('sf_forge_ui', '1');
    setForgeUiOverride(null);
    expect(localStorage.getItem('sf_forge_ui')).toBeNull();
  });

  it('after setForgeUiOverride(null), isForgeUiEnabled() falls back to false', () => {
    localStorage.setItem('sf_forge_ui', '1');
    setForgeUiOverride(null);
    expect(isForgeUiEnabled()).toBe(false);
  });
});
