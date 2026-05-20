"use client";

/**
 * settings-store — UI-only Zustand store for the Settings page.
 *
 * SECURITY: this store NEVER persists secrets (api_key, hf_token, bearer
 * tokens, etc.). API keys live in RHF form state and travel to the backend
 * via PUT /api/config — they are echoed back masked. We persist only:
 *
 *   - lastTab:           which tab the user opened last (defaults "general")
 *   - wizardDismissed:   if the user explicitly closed the first-run wizard
 *
 * Storage key namespace: `forge_settings_*` (parity with reader-store).
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export type SettingsTabId = "general" | "api-keys" | "advanced-l1" | "advanced-l2";

interface SettingsUiState {
  lastTab: SettingsTabId;
  wizardDismissed: boolean;
  setLastTab: (tab: SettingsTabId) => void;
  dismissWizard: () => void;
  resetWizard: () => void;
}

export const useSettingsStore = create<SettingsUiState>()(
  persist(
    (set) => ({
      lastTab: "general",
      wizardDismissed: false,
      setLastTab: (lastTab) => set({ lastTab }),
      dismissWizard: () => set({ wizardDismissed: true }),
      resetWizard: () => set({ wizardDismissed: false }),
    }),
    {
      name: "forge_settings_ui",
      // Explicit whitelist — any future field must be opted-in here, so a
      // refactor cannot accidentally start persisting a secret.
      partialize: (s) => ({
        lastTab: s.lastTab,
        wizardDismissed: s.wizardDismissed,
      }),
    },
  ),
);
