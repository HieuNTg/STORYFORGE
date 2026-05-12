/**
 * StoryForge — Alpine.js app bootstrap.
 *
 * Registers all Alpine stores (app, pipeline, settings, i18n, flags) and
 * kicks off initial data loads.
 *
 * Stores are defined in web/js/stores/ and imported here.
 * This file owns only the bootstrap wiring — store logic lives in stores/.
 */

import { isForgeUiEnabled } from './feature-flags';
import { registerStores } from './stores/index';

// i18n is loaded via separate <script> tag and exposed as window.__sf_i18n
const i18n = window.__sf_i18n;

/* ── Alpine init ── */
document.addEventListener('alpine:init', () => {

  Alpine.store('i18n', i18n);

  // Feature flags store — read-only snapshot at boot time.
  // To toggle at runtime use setForgeUiOverride() then reload.
  Alpine.store('flags', {
    forgeUi: isForgeUiEnabled(),
  });

  // Register app, pipeline, settings stores from stores/ modules.
  // Store keys ('app', 'pipeline', 'settings') and all field shapes are
  // identical to the original inline definitions — pure refactor, no behavior change.
  registerStores();

  // Init: load choices and config
  Alpine.store('pipeline').loadChoices();
  Alpine.store('pipeline').loadTemplates();
  Alpine.store('settings').load();
});
