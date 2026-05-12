/**
 * GenreOrb — Alpine.data factory for the decorative landing/library genre orb.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.5
 *
 * Per-genre hue is supplied as a CSS color and applied through the
 * --orb-hue custom property. The orb is decorative on landing/library
 * cards (aria-hidden="true"); on the Pipeline page it acts as a radio
 * (set decorative=false to expose role="radio" semantics).
 *
 * CSS-only animation: glow + hover lift + (selected) ripple. Reduced-motion
 * fallback is handled in components.css.
 *
 * Usage (decorative — landing/library):
 *   <span x-data="genreOrb({ genreId: 'tien-hiep', hue: '#10B981' })"
 *         class="sf-genre-orb"
 *         :style="orbStyle"
 *         aria-hidden="true">
 *   </span>
 *
 * Usage (interactive — pipeline radio group):
 *   <button x-data="genreOrb({ genreId: 'tien-hiep', hue: '#10B981',
 *                              label: 'Tiên Hiệp', decorative: false,
 *                              selected: $store.pipeline.form.genre === 'tien-hiep' })"
 *           class="sf-genre-orb"
 *           :style="orbStyle"
 *           role="radio"
 *           :aria-checked="ariaChecked"
 *           :aria-label="label"
 *           @click="handleClick">
 *   </button>
 */

export type GenreId = string;

export interface GenreOrbProps {
  genreId: GenreId;
  /** CSS color value applied to --orb-hue. */
  hue: string;
  /** Optional accessible label. Only used when decorative=false. */
  label?: string;
  /** True if this orb is decorative (default true → aria-hidden). */
  decorative?: boolean;
  /** Selection state when used as a radio item. */
  selected?: boolean;
}

export interface GenreOrbComponent {
  genreId: GenreId;
  hue: string;
  label: string;
  decorative: boolean;
  selected: boolean;
  readonly orbStyle: string;
  readonly ariaChecked: 'true' | 'false';
  readonly ariaHidden: 'true' | undefined;
  setSelected(next: boolean): void;
  handleClick(event?: Event): void;
}

/**
 * Default genre → hue mapping (matches PRD §5.1).
 * Used by templates that don't supply an explicit hue.
 */
export const GENRE_HUE: Readonly<Record<string, string>> = Object.freeze({
  'tien-hiep':    '#10B981',
  'do-thi':       '#F43F5E',
  'huyen-huyen':  '#8B5CF6',
  'xuyen-khong':  '#F59E0B',
});

export function genreOrb(props: GenreOrbProps): GenreOrbComponent {
  const decorative = props.decorative ?? true;
  return {
    genreId: props.genreId,
    hue: props.hue,
    label: props.label ?? props.genreId,
    decorative,
    selected: props.selected ?? false,

    get orbStyle(): string {
      // Inline custom property; safe to consume from CSS via var(--orb-hue).
      return `--orb-hue: ${this.hue};`;
    },

    get ariaChecked(): 'true' | 'false' {
      return this.selected ? 'true' : 'false';
    },

    get ariaHidden(): 'true' | undefined {
      return this.decorative ? 'true' : undefined;
    },

    setSelected(next: boolean): void {
      this.selected = next;
    },

    handleClick(event?: Event): void {
      // Decorative orbs are non-interactive. Templates should not bind @click
      // when decorative=true, but if they do we no-op silently.
      if (this.decorative) {
        event?.preventDefault();
        return;
      }

      const ctx = this as unknown as { $dispatch?: (n: string, d?: unknown) => void };
      if (typeof ctx.$dispatch === 'function') {
        ctx.$dispatch('sf:genre-selected', {
          genreId: this.genreId,
          hue: this.hue,
        });
      }
    },
  };
}
