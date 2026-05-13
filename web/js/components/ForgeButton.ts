/**
 * ForgeButton — Alpine.data factory for the primary action button.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.1
 *
 * Variants: primary | secondary | danger | ghost (via [data-variant])
 * States:   idle | hover | active | loading | disabled (via [data-state])
 * ARIA:     aria-busy when loading, aria-disabled mirrors disabled.
 *
 * Usage:
 *   <button x-data="forgeButton({ label: 'Forge Story', variant: 'primary' })"
 *           class="sf-forge-btn"
 *           :data-variant="variant"
 *           :data-state="state"
 *           :aria-busy="state === 'loading'"
 *           :aria-disabled="disabled || state === 'disabled'"
 *           :disabled="disabled || state === 'disabled'"
 *           @click="handleClick">
 *     <span x-text="label"></span>
 *   </button>
 */

export type ForgeButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ForgeButtonState = 'idle' | 'hover' | 'active' | 'loading' | 'disabled';

export interface ForgeButtonProps {
  label?: string;
  variant?: ForgeButtonVariant;
  state?: ForgeButtonState;
  disabled?: boolean;
}

export interface ForgeButtonComponent {
  label: string;
  variant: ForgeButtonVariant;
  state: ForgeButtonState;
  disabled: boolean;
  readonly ariaBusy: 'true' | 'false';
  readonly ariaDisabled: 'true' | 'false';
  setState(next: ForgeButtonState): void;
  handleClick(event?: Event): void;
}

/**
 * Build a ForgeButton component instance.
 *
 * Returns a plain object suitable for Alpine.data registration.
 * Behavior is pure — no DOM access in the factory; all side effects
 * happen via Alpine bindings on the template element.
 */
export function forgeButton(
  props: ForgeButtonProps = {},
): ForgeButtonComponent {
  const initialState: ForgeButtonState = props.state ?? 'idle';
  const initialDisabled = props.disabled ?? false;

  return {
    label: props.label ?? 'Forge Story',
    variant: props.variant ?? 'primary',
    state: initialState,
    disabled: initialDisabled,

    get ariaBusy(): 'true' | 'false' {
      return this.state === 'loading' ? 'true' : 'false';
    },

    get ariaDisabled(): 'true' | 'false' {
      return this.disabled || this.state === 'disabled' ? 'true' : 'false';
    },

    setState(next: ForgeButtonState): void {
      this.state = next;
    },

    handleClick(event?: Event): void {
      // Block clicks when loading or disabled. Native [disabled] also blocks,
      // but we early-return here so consumers can listen on @click without
      // re-checking state.
      if (
        this.disabled ||
        this.state === 'disabled' ||
        this.state === 'loading'
      ) {
        event?.preventDefault();
        event?.stopPropagation();
        return;
      }

      // Dispatch a sf:forge-click event so parent containers can react
      // without coupling to the button instance directly. The Alpine
      // template binds @click="handleClick($event)" — $dispatch is invoked
      // through the AlpineComponent context when `this.$dispatch` exists.
      const ctx = this as unknown as { $dispatch?: (n: string, d?: unknown) => void };
      if (typeof ctx.$dispatch === 'function') {
        ctx.$dispatch('sf:forge-click', { state: this.state });
      }
    },
  };
}
