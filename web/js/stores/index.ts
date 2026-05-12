/**
 * stores/index.ts — registers all Alpine stores.
 *
 * Call registerStores() once inside 'alpine:init'.
 * Store keys are unchanged from the original app.ts definitions:
 *   'app', 'pipeline', 'settings'
 * (i18n and flags stores are registered directly in app.ts bootstrap
 *  since they depend on values computed before this module loads.)
 */

import { createAppStore } from './app';
import { createPipelineStore } from './pipeline';
import { createSettingsStore } from './settings';

export function registerStores(): void {
  Alpine.store('app', createAppStore());
  Alpine.store('pipeline', createPipelineStore());
  Alpine.store('settings', createSettingsStore());
}

export { createAppStore, createPipelineStore, createSettingsStore };
