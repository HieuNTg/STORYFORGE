"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface QualityGaugeProps {
  value: number;
  label?: string;
  className?: string;
  size?: number;
  /** Layer index (1, 2, ...) the score belongs to, shown as a small caption. */
  layer?: number;
  /** Epoch ms of the latest update; drives "vừa cập nhật" caption. */
  updatedAt?: number;
}

const ARC_DEGREES = 270;
const START_ANGLE = 135;

function polar(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function arcPath(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const start = polar(cx, cy, r, endDeg);
  const end = polar(cx, cy, r, startDeg);
  const largeArc = endDeg - startDeg <= 180 ? 0 : 1;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}

/** Friendly "X giây/phút trước" caption that re-renders every 30s. */
function useRelativeCaption(updatedAt?: number): string | null {
  const [now, setNow] = React.useState<number>(() => Date.now());
  React.useEffect(() => {
    if (!updatedAt) return;
    const id = window.setInterval(() => setNow(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, [updatedAt]);
  if (!updatedAt) return null;
  const diff = Math.max(0, now - updatedAt);
  if (diff < 5_000) return "Vừa cập nhật";
  if (diff < 60_000) return `${Math.round(diff / 1000)}s trước`;
  if (diff < 60 * 60_000) return `${Math.round(diff / 60_000)} phút trước`;
  return `${Math.round(diff / (60 * 60_000))} giờ trước`;
}

export function QualityGauge({
  value,
  label = "Chất lượng",
  className,
  size = 160,
  layer,
  updatedAt,
}: QualityGaugeProps) {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const stroke = 10;
  const r = (size - stroke) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const endAngle = START_ANGLE + ARC_DEGREES;
  const path = arcPath(cx, cy, r, START_ANGLE, endAngle);

  // Approximate path length: arc length = 2πr * (deg/360)
  const length = (2 * Math.PI * r * ARC_DEGREES) / 360;
  const visible = (length * clamped) / 100;
  const hidden = length - visible;

  // One-shot ease-out: start fully hidden, transition to target on mount.
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);

  // Tween the displayed number between successive `value` updates.
  const [display, setDisplay] = React.useState(clamped);
  const prevRef = React.useRef(clamped);
  React.useEffect(() => {
    const from = prevRef.current;
    const to = clamped;
    if (from === to) return;
    prevRef.current = to;
    const start = performance.now();
    const dur = 360;
    let raf = 0;
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / dur);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - k, 3);
      setDisplay(Math.round(from + (to - from) * eased));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [clamped]);

  const caption = useRelativeCaption(updatedAt);

  return (
    <div className={cn("flex flex-col items-center gap-2", className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label={`${label}: ${clamped} trên 100`}
        >
          <path
            d={path}
            fill="none"
            stroke="var(--border)"
            strokeWidth={stroke}
            strokeLinecap="round"
          />
          <path
            d={path}
            fill="none"
            stroke="var(--accent)"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${length} ${length}`}
            strokeDashoffset={mounted ? hidden : length}
            style={{
              transition:
                "stroke-dashoffset var(--duration-slow, 320ms) var(--ease-out, ease-out)",
            }}
          />
        </svg>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-semibold tabular-nums text-foreground">
            {display}
          </span>
          <span className="text-xs text-muted-foreground">{label}</span>
        </div>
      </div>
      {(typeof layer === "number" || caption) && (
        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
          {typeof layer === "number" ? (
            <span className="rounded-full border border-border/60 px-1.5 py-0.5">
              Layer {layer}
            </span>
          ) : null}
          {caption ? <span aria-live="polite">{caption}</span> : null}
        </div>
      )}
    </div>
  );
}
