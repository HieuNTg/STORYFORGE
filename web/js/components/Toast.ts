/**
 * Toast — global notification system.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.10
 *
 * Two pieces ship in one module:
 *
 *   1. `createToastStore()` — Alpine.store('toasts') singleton. Owns the
 *      stack of active toasts plus push/dismiss APIs.
 *
 *   2. `toastItem(props)` — Alpine.data factory bound to each `<li>` rendered
 *      by the region template. Owns per-toast state (visible / paused).
 *
 * The region root is split in two so error/warning toasts can use
 * aria-live="assertive" while info/success use aria-live="polite"
 * (WCAG 2.1 — never interrupt for routine info).
 *
 * Reduced-motion: CSS handles the swap (fade only, no slide). Auto-dismiss
 * timers still run; they just lose the slide-out animation.
 */

export type ToastVariant = 'info' | 'success' | 'warning' | 'error';

export interface ToastItem {
  id: string;
  message: string;
  variant: ToastVariant;
  /** ms; 0 = sticky (no auto-dismiss). */
  durationMs: number;
  /** Wall-clock ms when this toast was first pushed. */
  createdAt: number;
}

export interface ToastInput {
  message: string;
  variant?: ToastVariant;
  /** ms; 0 = sticky. Defaults: info/success=5000, warning=6000, error=8000. */
  durationMs?: number;
}

export interface ToastStore {
  items: ToastItem[];
  push(input: ToastInput): string;
  dismiss(id: string): void;
  clear(): void;
  /** Returns true if the variant should live in the assertive region. */
  isAssertive(variant: ToastVariant): boolean;
}

const DEFAULT_DURATIONS: Readonly<Record<ToastVariant, number>> = Object.freeze({
  info: 5000,
  success: 5000,
  warning: 6000,
  error: 8000,
});

/**
 * Build the Alpine.store('toasts') singleton.
 *
 * `Alpine.store('toasts', createToastStore())` at bootstrap.
 *
 * The dismiss timer is scheduled via setTimeout; Alpine reactivity picks up
 * the array mutation automatically because the store is a plain object that
 * Alpine proxies on registration. We avoid keeping a Map of timers on the
 * store itself (would be non-serialisable) — instead each timer is closed
 * over and self-cancels by checking the items array.
 */
export function createToastStore(): ToastStore {
  // Counter used together with a random suffix to mint unique ids without
  // pulling in a uuid dependency.
  let counter = 0;
  const mintId = (): string => {
    counter += 1;
    return `tst-${Date.now().toString(36)}-${counter.toString(36)}`;
  };

  const store: ToastStore = {
    items: [] as ToastItem[],

    push(input: ToastInput): string {
      const variant = input.variant ?? 'info';
      const durationMs =
        input.durationMs ?? DEFAULT_DURATIONS[variant] ?? DEFAULT_DURATIONS.info;
      const item: ToastItem = {
        id: mintId(),
        message: input.message,
        variant,
        durationMs,
        createdAt: Date.now(),
      };
      this.items.push(item);

      if (durationMs > 0 && typeof globalThis.setTimeout === 'function') {
        // Defer auto-dismiss. The closure captures `this`; since the store is
        // a singleton on Alpine.store('toasts'), the same reference is alive
        // for the timer's lifetime.
        const ref = this;
        globalThis.setTimeout(() => {
          ref.dismiss(item.id);
        }, durationMs);
      }
      return item.id;
    },

    dismiss(id: string): void {
      const idx = this.items.findIndex((t) => t.id === id);
      if (idx >= 0) {
        this.items.splice(idx, 1);
      }
    },

    clear(): void {
      this.items.splice(0, this.items.length);
    },

    isAssertive(variant: ToastVariant): boolean {
      return variant === 'warning' || variant === 'error';
    },
  };

  return store;
}

/* ── Per-toast Alpine.data factory ───────────────────────────────────────── */

export interface ToastItemProps {
  toast: ToastItem;
}

export interface ToastItemComponent {
  toast: ToastItem;
  readonly role: 'status' | 'alert';
  readonly ariaLive: 'polite' | 'assertive';
  dismiss(): void;
}

/**
 * Per-toast factory. Rendered inside the region template:
 *
 *   <template x-for="t in $store.toasts.items" :key="t.id">
 *     <li x-data="toastItem({ toast: t })" :role="role" :aria-live="ariaLive"
 *         class="sf-toast" :data-variant="toast.variant"
 *         @click="dismiss()">
 *       …
 *     </li>
 *   </template>
 *
 * The factory holds no internal state beyond the toast prop; dismiss delegates
 * to the store so the source of truth stays in one place.
 */
export function toastItem(props: ToastItemProps): ToastItemComponent {
  const t = props.toast;
  return {
    toast: t,

    get role(): 'status' | 'alert' {
      return t.variant === 'warning' || t.variant === 'error' ? 'alert' : 'status';
    },

    get ariaLive(): 'polite' | 'assertive' {
      return t.variant === 'warning' || t.variant === 'error' ? 'assertive' : 'polite';
    },

    dismiss(): void {
      // Resolve the store at call time (Alpine attaches $store at runtime).
      const ctx = this as unknown as { $store?: { toasts?: ToastStore } };
      if (ctx.$store?.toasts) {
        ctx.$store.toasts.dismiss(this.toast.id);
      }
    },
  };
}

/* ── Convenience window helper ───────────────────────────────────────────── */

/**
 * Wider Forge UI signature for `window.sfShowToast`. The legacy declaration
 * in globals.d.ts (driven by web/js/error-boundary.ts) is intentionally
 * narrower — it only handles 'error' / 'warning' and returns void. The
 * Forge bootstrap reassigns the global to a wider implementation that
 * accepts any of the four toast variants plus an optional duration. We
 * cast at the assignment site rather than widen the global declaration
 * so existing callers (error-boundary.ts) stay type-clean.
 */
export type SfShowToastFn = (
  message: string,
  variant?: ToastVariant,
  durationMs?: number,
) => string;

/**
 * Bind `window.sfShowToast` to the registered store. Called from app.ts
 * bootstrap after `Alpine.store('toasts', …)` has run.
 */
export function attachWindowHelper(store: ToastStore): void {
  if (typeof window === 'undefined') return;
  const wider: SfShowToastFn = (message, variant, durationMs) => {
    return store.push({ message, variant, durationMs });
  };
  // Cast through unknown because the global declaration is intentionally
  // narrower (legacy error-boundary signature). The wider runtime function
  // is forward-compatible — old two-arg callers still receive a string id
  // (silently ignored by the legacy `: void` return).
  (window as unknown as { sfShowToast: SfShowToastFn }).sfShowToast = wider;
}

export const TOAST_DEFAULT_DURATIONS = DEFAULT_DURATIONS;
