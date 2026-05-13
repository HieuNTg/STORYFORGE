/**
 * QualityGauge — Alpine.data factory for the SVG quality-score arc.
 *
 * Spec: plans/260512-1949-uiux-prd-implementation/02-ux-architecture.md §2.8
 *
 * The factory is a pure presenter exposing:
 *   - normalized 0..1 value (regardless of input scale)
 *   - color band lookup (danger / forge / complete)
 *   - arc geometry (stroke-dasharray / stroke-dashoffset) so the template
 *     can animate fill via CSS transition without JS rAF
 *   - radar polygon points when `dimensions` is provided
 *   - state machine: empty → scoring → scored
 *
 * Binds at the `done` event to `done.data.quality[]` entries (see
 * api/pipeline_output_builder.py): each entry has overall + coherence +
 * character + drama + writing. Parent picks the dimension to render.
 *
 * Reduced-motion handled by CSS (transition: none on the dashoffset rule
 * under @media (prefers-reduced-motion: reduce)). The factory exposes
 * `prefersReducedMotion` so the template can suppress the bounce keyframe
 * when needed without re-detecting.
 */

export type GaugeScale = '0-1' | '0-5';
export type GaugeSize = 'sm' | 'md' | 'lg';
export type GaugeState = 'empty' | 'scoring' | 'scored';
export type GaugeBand = 'danger' | 'forge' | 'complete';

export interface GaugeDimension {
  name: string;
  /** Value in the same scale as the parent gauge. */
  value: number;
}

export interface QualityGaugeProps {
  value?: number;
  scale?: GaugeScale;
  label?: string;
  size?: GaugeSize;
  dimensions?: GaugeDimension[];
  prefersReducedMotion?: boolean;
}

/** Geometry for the SVG template. Coords are in a 100x100 viewBox centered at (50,50). */
export interface GaugeGeometry {
  cx: number;
  cy: number;
  radius: number;
  circumference: number;
  /** Length of the visible arc (stroke-dasharray needs this + total). */
  visibleLength: number;
  /** stroke-dasharray="<visible> <total>" string ready for template binding. */
  dasharray: string;
  /** stroke-dashoffset value (decreases as progress increases). */
  dashoffset: number;
  /** Endpoint of the arc — drives the end-marker circle position. */
  endpoint: { x: number; y: number };
}

export interface QualityGaugeComponent {
  value: number;
  scale: GaugeScale;
  label: string;
  size: GaugeSize;
  dimensions: GaugeDimension[];
  state: GaugeState;
  prefersReducedMotion: boolean;

  /** value normalized to [0,1] regardless of scale. */
  readonly progress: number;
  /** Display value formatted with one decimal (e.g. "3.4" for 0-5, "0.85" for 0-1). */
  readonly displayValue: string;
  /** Max for the configured scale (1 or 5). */
  readonly displayMax: number;
  /** Color band — drives the gauge stroke + end-marker fill via CSS data-band. */
  readonly band: GaugeBand;
  /** Pre-computed SVG geometry for the template to bind. */
  readonly geometry: GaugeGeometry;
  /** "Quality score: <value> out of <max>" — aria-label and SVG <title>. */
  readonly ariaLabel: string;
  /** Polygon points for the multi-dim radar chart. Empty string when no dimensions. */
  readonly radarPoints: string;
  /** Whether the multi-dim radar should render. */
  readonly hasRadar: boolean;

  setValue(next: number): void;
  setDimensions(next: GaugeDimension[] | undefined): void;
  setState(next: GaugeState): void;
}

const GAUGE_RADIUS = 42; // Inside a 100x100 viewBox with 50/50 center → leaves room for stroke + end-marker.
const GAUGE_CENTER = 50;

/** 270° arc — top-left to top-right, opening at the bottom. The classic gauge shape. */
const ARC_SWEEP_FRACTION = 0.75;

function clamp01(n: number): number {
  if (!Number.isFinite(n)) return 0;
  if (n < 0) return 0;
  if (n > 1) return 1;
  return n;
}

function normalize(value: number, scale: GaugeScale): number {
  if (!Number.isFinite(value)) return 0;
  if (scale === '0-5') return clamp01(value / 5);
  return clamp01(value);
}

function bandFor(progress: number): GaugeBand {
  if (progress < 0.4) return 'danger';
  if (progress < 0.7) return 'forge';
  return 'complete';
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

/**
 * Compute the (x, y) for the arc endpoint given a 0..1 progress along the visible arc.
 * Arc starts at 135° (bottom-left), sweeps clockwise to 45° (bottom-right).
 * progress=0 → start point; progress=1 → end point.
 */
function arcEndpoint(progress: number): { x: number; y: number } {
  // Start angle = 135° (measured from 12 o'clock, clockwise). End angle = 405° (135° + 270°).
  const startDeg = 135;
  const sweepDeg = 270;
  const angleDeg = startDeg + sweepDeg * clamp01(progress);
  const angleRad = ((angleDeg - 90) * Math.PI) / 180; // SVG convention: 0° at 3 o'clock.
  return {
    x: GAUGE_CENTER + GAUGE_RADIUS * Math.cos(angleRad),
    y: GAUGE_CENTER + GAUGE_RADIUS * Math.sin(angleRad),
  };
}

/**
 * Compute the radar polygon points for N dimensions. Each axis is evenly spaced
 * around the gauge ring at GAUGE_RADIUS * 0.6 (so the radar sits inside the arc).
 * Returns an SVG `points=""` string (space-separated "x,y" pairs).
 */
function computeRadarPoints(
  dimensions: GaugeDimension[],
  scale: GaugeScale,
): string {
  if (dimensions.length < 3) return '';
  const innerRadius = GAUGE_RADIUS * 0.6;
  const step = (Math.PI * 2) / dimensions.length;
  const startAngle = -Math.PI / 2; // First axis points up.
  return dimensions
    .map((d, i) => {
      const norm = normalize(d.value, scale);
      const angle = startAngle + step * i;
      const r = innerRadius * norm;
      const x = GAUGE_CENTER + r * Math.cos(angle);
      const y = GAUGE_CENTER + r * Math.sin(angle);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

export function qualityGauge(props: QualityGaugeProps = {}): QualityGaugeComponent {
  const scale: GaugeScale = props.scale === '0-5' ? '0-5' : '0-1';
  const label = typeof props.label === 'string' ? props.label : '';
  const size: GaugeSize = props.size ?? 'md';
  const dimensions = Array.isArray(props.dimensions) ? props.dimensions.slice() : [];
  const initialValue = Number.isFinite(props.value) ? (props.value as number) : 0;
  const reducedMotion =
    typeof props.prefersReducedMotion === 'boolean'
      ? props.prefersReducedMotion
      : detectReducedMotion();

  return {
    value: initialValue,
    scale,
    label,
    size,
    dimensions,
    state: initialValue > 0 ? 'scored' : 'empty',
    prefersReducedMotion: reducedMotion,

    get progress(): number {
      return normalize(this.value, this.scale);
    },

    get displayMax(): number {
      return this.scale === '0-5' ? 5 : 1;
    },

    get displayValue(): string {
      if (this.scale === '0-5') {
        return this.value.toFixed(1);
      }
      return this.value.toFixed(2);
    },

    get band(): GaugeBand {
      return bandFor(this.progress);
    },

    get geometry(): GaugeGeometry {
      const circumference = 2 * Math.PI * GAUGE_RADIUS;
      const arcLength = circumference * ARC_SWEEP_FRACTION;
      const visibleLength = arcLength * this.progress;
      return {
        cx: GAUGE_CENTER,
        cy: GAUGE_CENTER,
        radius: GAUGE_RADIUS,
        circumference,
        visibleLength,
        dasharray: `${arcLength} ${circumference}`,
        dashoffset: arcLength - visibleLength,
        endpoint: arcEndpoint(this.progress),
      };
    },

    get ariaLabel(): string {
      const prefix = this.label ? `${this.label} ` : '';
      return `${prefix}Quality score: ${this.displayValue} out of ${this.displayMax}`.trim();
    },

    get radarPoints(): string {
      return computeRadarPoints(this.dimensions, this.scale);
    },

    get hasRadar(): boolean {
      return this.dimensions.length >= 3;
    },

    setValue(next: number): void {
      if (!Number.isFinite(next)) return;
      this.value = next;
      this.state = next > 0 ? 'scored' : 'empty';
    },

    setDimensions(next: GaugeDimension[] | undefined): void {
      this.dimensions = Array.isArray(next) ? next.slice() : [];
    },

    setState(next: GaugeState): void {
      if (next === 'empty' || next === 'scoring' || next === 'scored') {
        this.state = next;
      }
    },
  };
}
