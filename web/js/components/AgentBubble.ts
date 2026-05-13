/**
 * AgentBubble — Alpine.data factory for the per-agent debate surface.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.3
 *
 * Live state is fed externally by sniffers (see web/js/stores/sse-sniffers.ts);
 * the bubble is a dumb presenter. Parent — pipeline page — owns the orchestration:
 *   - sniffAgentTurn(msg)    → setSpeaking(name, action)
 *   - sniffAgentsPhase(msg)  → setPhase('approved'|'revision', layer)
 *   - sniffDebateMarker(msg) → setDebating()
 *
 * Typewriter effect is implemented via a step counter (`revealedChars`) the
 * template binds with `clip-path: inset(0 calc(100% - var(--reveal,100%)) 0 0)`.
 * The factory exposes `startTypewriter(text)` so the parent can also drive
 * reveals from outside Alpine's reactivity if needed (tests, manual ticks).
 *
 * A11y contract:
 *   role="status", aria-live="polite", aria-label="<name> agent, currently <state>".
 *
 * Reduced-motion: typewriter falls back to instant render — the factory
 * checks `prefers-reduced-motion: reduce` once at construction and skips the
 * step ticker. CSS handles shake/pulse fallbacks separately.
 */

export type AgentState =
  | 'idle'
  | 'thinking'
  | 'speaking'
  | 'debating'
  | 'voting'
  | 'done';

export interface AgentBubbleProps {
  agentId: string;
  name: string;
  avatar?: string;
  state?: AgentState;
  message?: string;
  /** 0..1, used for the voting state. */
  score?: number;
  /** Sidebar mode — denser layout. */
  compact?: boolean;
  /**
   * Optional override for reduced-motion detection.
   *   - true  → skip typewriter even if user has no preference
   *   - false → force typewriter even if user prefers reduced motion
   * Default: read from `window.matchMedia('(prefers-reduced-motion: reduce)')`.
   */
  prefersReducedMotion?: boolean;
  /** Milliseconds per typewriter step. Defaults to 25ms per the spec. */
  typewriterStepMs?: number;
}

export interface AgentBubbleComponent {
  agentId: string;
  name: string;
  avatar: string;
  state: AgentState;
  message: string;
  score: number | null;
  compact: boolean;
  /** Number of characters currently revealed by the typewriter. */
  revealedChars: number;
  /** Internal: timer handle used by tick scheduler. Public for test inspection. */
  _typewriterTimer: ReturnType<typeof setTimeout> | null;
  _reducedMotion: boolean;
  _stepMs: number;
  readonly ariaLabel: string;
  /** CSS custom-prop value (0..100) for the reveal mask, suitable for inline style. */
  readonly revealPct: number;
  /** Score formatted as 0..100 integer for the voting state. Null when not voting. */
  readonly scorePct: number | null;
  setState(next: AgentState): void;
  setMessage(text: string): void;
  setScore(score: number | null): void;
  /** Manually advance the typewriter by one step. Returns true when more chars remain. */
  tickTypewriter(): boolean;
  /** Reset reveal counter to 0 and (re)start the ticker for the current message. */
  startTypewriter(text?: string): void;
  /** Cancel a running ticker without clearing the message. */
  stopTypewriter(): void;
  /** Click handler — dispatches sf:agent-clicked. */
  handleClick(event?: Event): void;
  /** Alpine lifecycle hook — wires $watch('message') to restart typewriter. */
  init(): void;
  /** Alpine lifecycle hook — stops any pending timer. */
  destroy(): void;
}

const STATE_VALUES: ReadonlyArray<AgentState> = [
  'idle',
  'thinking',
  'speaking',
  'debating',
  'voting',
  'done',
];

function isAgentState(value: unknown): value is AgentState {
  return typeof value === 'string' && (STATE_VALUES as ReadonlyArray<string>).includes(value);
}

function detectReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches === true;
  } catch {
    return false;
  }
}

function clampScore(score: number | undefined): number | null {
  if (score === undefined || score === null) return null;
  if (!Number.isFinite(score)) return null;
  if (score < 0) return 0;
  if (score > 1) return 1;
  return score;
}

export function agentBubble(props: AgentBubbleProps): AgentBubbleComponent {
  const initialState: AgentState = isAgentState(props.state) ? props.state : 'idle';
  const initialMessage = typeof props.message === 'string' ? props.message : '';
  const reducedMotion =
    typeof props.prefersReducedMotion === 'boolean'
      ? props.prefersReducedMotion
      : detectReducedMotion();
  const stepMs =
    Number.isFinite(props.typewriterStepMs) && (props.typewriterStepMs as number) > 0
      ? Math.floor(props.typewriterStepMs as number)
      : 25;

  return {
    agentId: props.agentId,
    name: props.name,
    avatar: props.avatar ?? '',
    state: initialState,
    message: initialMessage,
    score: clampScore(props.score),
    compact: props.compact === true,
    revealedChars: reducedMotion ? initialMessage.length : 0,
    _typewriterTimer: null,
    _reducedMotion: reducedMotion,
    _stepMs: stepMs,

    get ariaLabel(): string {
      return `${this.name} agent, currently ${this.state}`;
    },

    get revealPct(): number {
      const len = this.message.length;
      if (len === 0) return 100;
      const pct = (this.revealedChars / len) * 100;
      if (pct < 0) return 0;
      if (pct > 100) return 100;
      return pct;
    },

    get scorePct(): number | null {
      if (this.state !== 'voting') return null;
      if (this.score === null) return null;
      return Math.round(this.score * 100);
    },

    setState(next: AgentState): void {
      if (!isAgentState(next)) return;
      this.state = next;
    },

    setMessage(text: string): void {
      this.message = typeof text === 'string' ? text : '';
      this.startTypewriter();
    },

    setScore(score: number | null): void {
      this.score = clampScore(score === null ? undefined : score);
    },

    tickTypewriter(): boolean {
      if (this.revealedChars >= this.message.length) {
        this.stopTypewriter();
        return false;
      }
      this.revealedChars += 1;
      return this.revealedChars < this.message.length;
    },

    startTypewriter(text?: string): void {
      if (typeof text === 'string') {
        this.message = text;
      }
      this.stopTypewriter();
      if (this._reducedMotion || this.message.length === 0) {
        this.revealedChars = this.message.length;
        return;
      }
      this.revealedChars = 0;
      const schedule = (): void => {
        if (typeof setTimeout !== 'function') return;
        this._typewriterTimer = setTimeout(() => {
          const more = this.tickTypewriter();
          if (more) schedule();
        }, this._stepMs);
      };
      schedule();
    },

    stopTypewriter(): void {
      if (this._typewriterTimer !== null && typeof clearTimeout === 'function') {
        clearTimeout(this._typewriterTimer);
      }
      this._typewriterTimer = null;
    },

    handleClick(event?: Event): void {
      const ctx = this as unknown as { $dispatch?: (n: string, d?: unknown) => void };
      if (typeof ctx.$dispatch === 'function') {
        ctx.$dispatch('sf:agent-clicked', { agentId: this.agentId });
      }
      event?.stopPropagation?.();
    },

    init(): void {
      const ctx = this as unknown as {
        $watch?: (expr: string, cb: (val: unknown) => void) => void;
      };
      if (typeof ctx.$watch === 'function') {
        ctx.$watch('message', () => {
          this.startTypewriter();
        });
      }
      if (this.message.length > 0 && !this._reducedMotion) {
        this.startTypewriter();
      }
    },

    destroy(): void {
      this.stopTypewriter();
    },
  };
}
