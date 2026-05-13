/**
 * feature-flags.ts — StoryForge feature flag resolution.
 *
 * Resolution order (highest priority first):
 *   1. window.__STORYFORGE_FLAGS__.forgeUi  (server/build-time injection)
 *   2. localStorage 'sf_forge_ui' === '1'   (user override)
 *   3. false                                 (default — flag is OFF by default)
 *
 * Per CLAUDE.md rule 8: new flags default OFF.
 * Flag name: STORYFORGE_FORGE_UI
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
 *   2. localStorage 'sf_forge_ui' === '1'
 *   3. false (default)
 */
export function isForgeUiEnabled(): boolean {
  // 1. Window global (highest priority — server/build injection)
  if (
    typeof window !== 'undefined' &&
    window.__STORYFORGE_FLAGS__ !== undefined &&
    typeof window.__STORYFORGE_FLAGS__.forgeUi === 'boolean'
  ) {
    return window.__STORYFORGE_FLAGS__.forgeUi;
  }

  // 2. localStorage user override
  try {
    if (typeof localStorage !== 'undefined') {
      return localStorage.getItem('sf_forge_ui') === '1';
    }
  } catch (_) {
    // localStorage may be unavailable (e.g. private browsing, SSR)
  }

  // 3. Default: OFF
  return false;
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
