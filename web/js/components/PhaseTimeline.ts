/**
 * PhaseTimeline — Alpine.data factory rendering the 8-phase Forge pipeline.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.2
 *
 * Phases (in order, matching pipeline/orchestrator.py phases):
 *   theme → characters → outline → conflict → scenes → chapters → post → done
 *
 * States per phase: pending | active | done | error
 *
 * Reads from $store.pipeline (already extracted in Day-1).
 *
 * ARIA: root <ol role="progressbar" aria-valuenow=<index> aria-valuemin=0
 *       aria-valuemax=<phases.length>>; each <li> has aria-current="step"
 *       when active.
 */

export type PhaseId =
  | 'theme'
  | 'characters'
  | 'outline'
  | 'conflict'
  | 'scenes'
  | 'chapters'
  | 'post'
  | 'done';

export type PhaseStepState = 'pending' | 'active' | 'done' | 'error';

export interface PhaseDef {
  id: PhaseId;
  labelKey: string; // i18n key resolved by template via $store.i18n.t(...)
  layer: 1 | 2 | 3;
}

export interface PhaseTimelineProps {
  phases?: PhaseDef[];
  currentIndex?: number;
  status?: 'idle' | 'running' | 'done' | 'error' | 'interrupted';
}

export interface PhaseTimelineComponent {
  phases: PhaseDef[];
  currentIndex: number;
  status: 'idle' | 'running' | 'done' | 'error' | 'interrupted';
  readonly ariaValueNow: number;
  readonly ariaValueMax: number;
  stateFor(index: number): PhaseStepState;
  ariaCurrentFor(index: number): 'step' | undefined;
  setCurrentIndex(index: number): void;
  setStatus(next: PhaseTimelineComponent['status']): void;
}

export const DEFAULT_PHASES: ReadonlyArray<PhaseDef> = Object.freeze([
  { id: 'theme',      labelKey: 'phase.theme',      layer: 1 },
  { id: 'characters', labelKey: 'phase.characters', layer: 1 },
  { id: 'outline',    labelKey: 'phase.outline',    layer: 1 },
  { id: 'conflict',   labelKey: 'phase.conflict',   layer: 1 },
  { id: 'scenes',     labelKey: 'phase.scenes',     layer: 1 },
  { id: 'chapters',   labelKey: 'phase.chapters',   layer: 1 },
  { id: 'post',       labelKey: 'phase.post',       layer: 1 },
  { id: 'done',       labelKey: 'phase.done',       layer: 3 },
]);

/**
 * Build a PhaseTimeline component instance.
 *
 * The current index is the zero-based position of the active phase. When
 * status === 'done', every phase is reported as 'done'. When status === 'error',
 * the active phase (currentIndex) is reported as 'error'; preceding phases
 * remain 'done'.
 */
export function phaseTimeline(
  props: PhaseTimelineProps = {},
): PhaseTimelineComponent {
  const phases = props.phases ?? DEFAULT_PHASES.slice();
  return {
    phases,
    currentIndex: clampIndex(props.currentIndex ?? 0, phases.length),
    status: props.status ?? 'idle',

    get ariaValueNow(): number {
      if (this.status === 'done') return this.phases.length;
      return this.currentIndex;
    },

    get ariaValueMax(): number {
      return this.phases.length;
    },

    stateFor(index: number): PhaseStepState {
      if (this.status === 'done') return 'done';
      if (index < this.currentIndex) return 'done';
      if (index === this.currentIndex) {
        if (this.status === 'error') return 'error';
        if (this.status === 'running' || this.status === 'interrupted') return 'active';
        return 'pending';
      }
      return 'pending';
    },

    ariaCurrentFor(index: number): 'step' | undefined {
      return this.stateFor(index) === 'active' ? 'step' : undefined;
    },

    setCurrentIndex(index: number): void {
      this.currentIndex = clampIndex(index, this.phases.length);
    },

    setStatus(next): void {
      this.status = next;
    },
  };
}

function clampIndex(idx: number, length: number): number {
  if (!Number.isFinite(idx)) return 0;
  if (idx < 0) return 0;
  if (length === 0) return 0;
  if (idx > length - 1) return length - 1;
  return Math.floor(idx);
}
