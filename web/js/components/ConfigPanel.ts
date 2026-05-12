/**
 * ConfigPanel — Alpine.data factory for the pipeline configuration form.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.9
 *
 * The panel is a collapsible section (native <details> on the template side,
 * but state lives here so the same factory can drive non-<details> renders
 * e.g. tabs or modal bodies).
 *
 * Two-way binds to the supplied settings store (defaults to Alpine's
 * 'settings' store but injectable for unit tests).
 *
 * State per section:
 *   collapsed/expanded — visual disclosure
 *   dirty/clean        — modified since load (sticky until reset or save)
 *
 * ARIA: template renders <fieldset><legend> per section with <details> as
 * the disclosure widget; this factory exposes ariaDescribedBy / ariaInvalid
 * helpers for inputs that bind via x-bind.
 */

export type ConfigGroupId = 'llm' | 'pipeline' | 'l2' | 'media' | 'quality';

export interface ConfigDescriptor {
  id: ConfigGroupId;
  title: string;          // i18n key resolved by template
  description?: string;   // optional help text id
  fields: ConfigFieldDescriptor[];
}

export interface ConfigFieldDescriptor {
  key: string;            // dot-path into the settings config object
  label: string;          // i18n key
  type: 'text' | 'number' | 'toggle' | 'select' | 'preset';
  /** For 'select'/'preset' fields. Each option's value is what's written to the store. */
  options?: ReadonlyArray<{ value: string | number | boolean; label: string }>;
  help?: string;          // i18n key for help text
  /** Optional client-side validator. Return string = error message; '' or undefined = valid. */
  validate?: (value: unknown) => string | undefined;
}

export interface ConfigPanelProps {
  /** Section descriptor list — pipeline config tables (LLM, pipeline flags, L2 toggles, …). */
  descriptors: ConfigDescriptor[];
  /** Sections that should start expanded. Defaults to ['llm'] (primary section). */
  defaultExpanded?: ConfigGroupId[];
  /**
   * Settings store reference. If undefined, the factory will lazy-resolve
   * `Alpine.store('settings')` on first read so templates work without
   * injection. Tests pass an in-memory stub.
   */
  store?: ConfigSettingsLike;
}

/**
 * Minimal shape of the settings store the panel consumes. Matches
 * web/js/stores/settings.ts but typed narrowly to keep tests trivial.
 */
export interface ConfigSettingsLike {
  config: Record<string, unknown> | null;
  save?: (data: Record<string, unknown>) => Promise<void> | void;
}

export interface ConfigPanelComponent {
  descriptors: ConfigDescriptor[];
  expanded: Record<ConfigGroupId, boolean>;
  dirty: Record<ConfigGroupId, boolean>;
  errors: Record<string, string>;
  readonly anyDirty: boolean;
  isExpanded(group: ConfigGroupId): boolean;
  isDirty(group: ConfigGroupId): boolean;
  /** Returns 'true' | 'false' for aria-expanded. */
  ariaExpanded(group: ConfigGroupId): 'true' | 'false';
  /** Returns 'true' | undefined for aria-invalid (omit attribute when valid). */
  ariaInvalid(fieldKey: string): 'true' | undefined;
  errorFor(fieldKey: string): string;
  /** Stable id for aria-describedby (paired with the help text element). */
  helpIdFor(fieldKey: string): string;
  toggle(group: ConfigGroupId): void;
  /** Mark a field as changed; validates and stamps the owning group dirty. */
  notifyChange(group: ConfigGroupId, fieldKey: string, value: unknown): void;
  /** Clear dirty + errors (e.g. after successful save). */
  reset(): void;
}

export function configPanel(props: ConfigPanelProps): ConfigPanelComponent {
  const descriptors = props.descriptors ?? [];
  const defaultExpanded = new Set(props.defaultExpanded ?? ['llm']);

  const expanded = {} as Record<ConfigGroupId, boolean>;
  const dirty = {} as Record<ConfigGroupId, boolean>;
  for (const d of descriptors) {
    expanded[d.id] = defaultExpanded.has(d.id);
    dirty[d.id] = false;
  }

  const fieldGroup = new Map<string, ConfigGroupId>();
  const validators = new Map<string, ConfigFieldDescriptor['validate']>();
  for (const d of descriptors) {
    for (const f of d.fields) {
      fieldGroup.set(f.key, d.id);
      if (f.validate) validators.set(f.key, f.validate);
    }
  }

  return {
    descriptors,
    expanded,
    dirty,
    errors: {} as Record<string, string>,

    get anyDirty(): boolean {
      for (const id in this.dirty) {
        if (this.dirty[id as ConfigGroupId]) return true;
      }
      return false;
    },

    isExpanded(group: ConfigGroupId): boolean {
      return !!this.expanded[group];
    },

    isDirty(group: ConfigGroupId): boolean {
      return !!this.dirty[group];
    },

    ariaExpanded(group: ConfigGroupId): 'true' | 'false' {
      return this.expanded[group] ? 'true' : 'false';
    },

    ariaInvalid(fieldKey: string): 'true' | undefined {
      return this.errors[fieldKey] ? 'true' : undefined;
    },

    errorFor(fieldKey: string): string {
      return this.errors[fieldKey] ?? '';
    },

    helpIdFor(fieldKey: string): string {
      // Slugify field key to a DOM-safe id for aria-describedby. Underscores
      // are valid in HTML ids — only non-alphanumeric/non-hyphen/non-underscore
      // characters are replaced.
      return `sf-cfg-help-${fieldKey.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
    },

    toggle(group: ConfigGroupId): void {
      // Reduced-motion is handled by CSS (no transition class); state flip is instant.
      this.expanded[group] = !this.expanded[group];
    },

    notifyChange(group: ConfigGroupId, fieldKey: string, value: unknown): void {
      // Authoritative group is whichever descriptor declared this field — fall
      // back to the passed group if the field is unknown (template typo etc.).
      const owner = fieldGroup.get(fieldKey) ?? group;
      this.dirty[owner] = true;

      const validate = validators.get(fieldKey);
      if (validate) {
        const msg = validate(value);
        if (msg) {
          this.errors[fieldKey] = msg;
        } else {
          delete this.errors[fieldKey];
        }
      }

      // Bubble for parent listeners (page-level save controls etc.). The same
      // pattern as the other Forge components.
      const ctx = this as unknown as { $dispatch?: (n: string, d?: unknown) => void };
      if (typeof ctx.$dispatch === 'function') {
        ctx.$dispatch('sf:config-changed', { group: owner, field: fieldKey, value });
      }
    },

    reset(): void {
      for (const id in this.dirty) this.dirty[id as ConfigGroupId] = false;
      this.errors = {};
    },
  };
}

/**
 * Minimal descriptor used by app.ts to render the Pipeline page advanced
 * panel out-of-the-box. Pages may pass their own descriptor list for custom
 * layouts; keeping a default here makes the component drop-in for Day-4
 * page wire-up.
 */
export const DEFAULT_CONFIG_DESCRIPTORS: ReadonlyArray<ConfigDescriptor> =
  Object.freeze([
    {
      id: 'llm',
      title: 'config.section.llm',
      fields: [
        { key: 'layer1_model', label: 'config.layer1_model', type: 'text' },
        { key: 'layer2_model', label: 'config.layer2_model', type: 'text' },
        { key: 'cheap_model',  label: 'config.cheap_model',  type: 'text' },
      ],
    },
    {
      id: 'pipeline',
      title: 'config.section.pipeline',
      fields: [
        { key: 'parallel_chapters_enabled', label: 'config.parallel_chapters', type: 'toggle' },
        { key: 'chapter_batch_size',        label: 'config.chapter_batch',     type: 'number' },
        { key: 'enable_scene_decomposition', label: 'config.scene_decomp',     type: 'toggle' },
        { key: 'enable_chapter_contracts',  label: 'config.chapter_contracts', type: 'toggle' },
        { key: 'enable_quality_gate',       label: 'config.quality_gate',      type: 'toggle' },
      ],
    },
    {
      id: 'l2',
      title: 'config.section.l2',
      fields: [
        { key: 'l2_consistency_engine', label: 'config.l2_engine',     type: 'toggle' },
        { key: 'l2_voice_preservation', label: 'config.l2_voice',      type: 'toggle' },
        { key: 'l2_drama_ceiling',      label: 'config.l2_drama',      type: 'toggle' },
        { key: 'l2_contract_gate',      label: 'config.l2_contract',   type: 'toggle' },
        { key: 'adaptive_simulation_rounds', label: 'config.adaptive_rounds', type: 'toggle' },
        { key: 'enable_structural_rewrite',  label: 'config.struct_rewrite',  type: 'toggle' },
      ],
    },
  ]) as ReadonlyArray<ConfigDescriptor>;
