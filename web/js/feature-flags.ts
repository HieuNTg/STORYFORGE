/**
 * feature-flags.ts — StoryForge feature flag resolution.
 *
 * Resolution order (highest priority first):
 *   1. window.__STORYFORGE_FLAGS__.forgeUi  (server/build-time injection)
 *   2. localStorage 'sf_forge_ui' === '1' / '0' (explicit user override)
 *   3. true                                  (default — Forge UI shipped sprint perf/forge-shell)
 *
 * Flag name: STORYFORGE_FORGE_UI
 * Status: shipped on (set default True). Per CLAUDE.md §8 the flag and its
 * dead-branch checks are scheduled for removal next sprint.
 */

declare global {
  interface Window {
    __STORYFORGE_FLAGS__?: {
      forgeUi?: boolean;
      [key: string]: boolean | undefined;
    };
  }
}

/**
 * Returns true if the Forge UI redesign is enabled.
 *
 * Resolution order:
 *   1. window.__STORYFORGE_FLAGS__.forgeUi (server-injected)
 *   2. localStorage 'sf_forge_ui' — '1' enables, '0' opts out, anything else falls through
 *   3. true (default — shipped sprint perf/forge-shell)
 */
export function isForgeUiEnabled(): boolean {
  if (
    typeof window !== 'undefined' &&
    window.__STORYFORGE_FLAGS__ !== undefined &&
    typeof window.__STORYFORGE_FLAGS__.forgeUi === 'boolean'
  ) {
    return window.__STORYFORGE_FLAGS__.forgeUi;
  }

  try {
    if (typeof localStorage !== 'undefined') {
      const override = localStorage.getItem('sf_forge_ui');
      if (override === '1') return true;
      if (override === '0') return false;
    }
  } catch (_) {
    // localStorage may be unavailable (e.g. private browsing, SSR)
  }

  return true;
}

/**
 * Set or clear the localStorage override for the Forge UI flag.
 *
 * @param enabled - true → sets override to '1', false → sets override to '0',
 *                  null → clears the override (falls through to window global or default).
 */
export function setForgeUiOverride(enabled: boolean | null): void {
  try {
    if (typeof localStorage === 'undefined') return;
    if (enabled === null) {
      localStorage.removeItem('sf_forge_ui');
    } else {
      localStorage.setItem('sf_forge_ui', enabled ? '1' : '0');
    }
  } catch (_) {
    // localStorage may be unavailable
  }
}
