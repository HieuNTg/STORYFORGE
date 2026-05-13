/**
 * StoryForge — Alpine.js app bootstrap.
 *
 * Registers all Alpine stores (app, pipeline, settings, i18n) and
 * kicks off initial data loads.
 *
 * Stores are defined in web/js/stores/ and imported here.
 * This file owns only the bootstrap wiring — store logic lives in stores/.
 */

import { registerStores } from './stores/index';
import { forgeButton } from './components/ForgeButton';
import { phaseTimeline } from './components/PhaseTimeline';
import { genreOrb } from './components/GenreOrb';
import { configPanel } from './components/ConfigPanel';
import { storyCard } from './components/StoryCard';
import { agentBubble } from './components/AgentBubble';
import { qualityGauge } from './components/QualityGauge';
import { characterGraph } from './components/CharacterGraph';
import { branchTree } from './components/BranchTree';
import { forgeBranchTreeMount } from './pages/branching';
import { forgeSettingsWizard } from './pages/settings';
import { forgeExportCards } from './pages/export';
import { createTheaterStore } from './stores/theater';
import { createReaderStore } from './stores/reader';
import {
  createToastStore,
  toastItem,
  attachWindowHelper as attachToastHelper,
} from './components/Toast';

// i18n is loaded via separate <script> tag and exposed as window.__sf_i18n
const i18n = window.__sf_i18n;

/* ── Alpine init ── */
document.addEventListener('alpine:init', () => {

  Alpine.store('i18n', i18n);

  // Register app, pipeline, settings stores from stores/ modules.
  // Store keys ('app', 'pipeline', 'settings') and all field shapes are
  // identical to the original inline definitions — pure refactor, no behavior change.
  registerStores();

  // Forge UI components — shipped on per CLAUDE.md §8 (STORYFORGE_FORGE_UI
  // flag removed sprint perf/forge-shell-2). The components are styled behind
  // :root[data-forge-ui="on"] (see components.css), and the attribute below
  // activates that gate.

  // Day-2 components.
  Alpine.data('forgeButton', forgeButton);
  Alpine.data('phaseTimeline', phaseTimeline);
  Alpine.data('genreOrb', genreOrb);

  // Day-3 components — defined but not yet referenced by any template.
  // Page integration ships in Day-4+ (library page redesign).
  Alpine.data('configPanel', configPanel);
  Alpine.data('storyCard', storyCard);
  Alpine.data('toastItem', toastItem);

  // M2 Day-2 — AgentBubble factory. Template integration arrives when the
  // pipeline page binds sniffers (sse-sniffers.ts) to per-agent state.
  Alpine.data('agentBubble', agentBubble);

  // M2 Day-3 — QualityGauge factory. Binds to done.data.quality[] entries
  // when the pipeline page is wired in Day-5.
  Alpine.data('qualityGauge', qualityGauge);

  // M2 Day-4 — CharacterGraph factory (d3-force + Canvas). Parent feeds
  // characters[] and relationships[] derived via stores/character-edges.ts
  // (co-occurrence heuristic, audit D2). Template wiring lands in Day-5.
  Alpine.data('characterGraph', characterGraph);

  // M3 BranchTree — Canvas-rendered branch tree replacing legacy SVG treeVisualizer.
  // Legacy treeVisualizer (tree-visualizer.ts) is untouched; both coexist.
  Alpine.data('branchTree', branchTree);

  // M3-tail: forgeBranchTreeMount — owns the fetch lifecycle for the BranchTree
  // canvas. Parent branchReader passes its sessionId via x-effect setSession().
  Alpine.data('forgeBranchTreeMount', forgeBranchTreeMount);

  // M4-B2: forgeSettingsWizard — guided 3-step wizard for first-time users.
  // Detects no-API-key state + sf:settings-wizard-dismissed localStorage flag.
  Alpine.data('forgeSettingsWizard', forgeSettingsWizard);

  // M4-B3: forgeExportCards — visual selectable format cards with slide-in
  // config panel. Falls through to exportPage() methods for actual download.
  Alpine.data('forgeExportCards', forgeExportCards);

  // M2 Day-5 — theater store. Pipeline-page derived state populated by
  // sniffers from the SSE log stream (see stores/pipeline.ts bridge).
  // Components (AgentBubble / QualityGauge / CharacterGraph) bind here.
  Alpine.store('theater', createTheaterStore());

  // M3 Day-1 — reader store. Typography + bookmark prefs, hydrated from
  // localStorage on construction.
  Alpine.store('reader', createReaderStore());

  // Toast store — singleton stack consumed by the toast region template.
  // attachToastHelper rebinds window.sfShowToast to the wider Forge
  // signature (4 variants + optional duration). Legacy two-arg callers
  // (error-boundary) keep working because the new function accepts both.
  const toastStore = createToastStore();
  Alpine.store('toasts', toastStore);
  attachToastHelper(toastStore);

  if (typeof document !== 'undefined' && document.documentElement) {
    document.documentElement.setAttribute('data-forge-ui', 'on');
  }

  // Init: load choices and config
  Alpine.store('pipeline').loadChoices();
  Alpine.store('pipeline').loadTemplates();
  Alpine.store('settings').load();
});
