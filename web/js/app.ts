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
import { forgeButton } from './components/ForgeButton';
import { phaseTimeline } from './components/PhaseTimeline';
import { genreOrb } from './components/GenreOrb';

// i18n is loaded via separate <script> tag and exposed as window.__sf_i18n
const i18n = window.__sf_i18n;

/* ── Alpine init ── */
document.addEventListener('alpine:init', () => {

  Alpine.store('i18n', i18n);

  // Feature flags store — read-only snapshot at boot time.
  // To toggle at runtime use setForgeUiOverride() then reload.
  const forgeUiOn = isForgeUiEnabled();
  Alpine.store('flags', {
    forgeUi: forgeUiOn,
  });

  // Register app, pipeline, settings stores from stores/ modules.
  // Store keys ('app', 'pipeline', 'settings') and all field shapes are
  // identical to the original inline definitions — pure refactor, no behavior change.
  registerStores();

  // Forge UI components — registered ONLY when the flag is on so the legacy
  // surface stays byte-identical for everyone else. The components themselves
  // are styled behind :root[data-forge-ui="on"] (see components.css), and the
  // attribute below activates that gate.
  if (forgeUiOn) {
    Alpine.data('forgeButton', forgeButton);
    Alpine.data('phaseTimeline', phaseTimeline);
    Alpine.data('genreOrb', genreOrb);
    if (typeof document !== 'undefined' && document.documentElement) {
      document.documentElement.setAttribute('data-forge-ui', 'on');
    }
  }

  // Init: load choices and config
  Alpine.store('pipeline').loadChoices();
  Alpine.store('pipeline').loadTemplates();
  Alpine.store('settings').load();
});
