"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface QualityGaugeProps {
  value: number;
  label?: string;
  className?: string;
  size?: number;
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

export function QualityGauge({
  value,
  label = "Chất lượng",
  className,
  size = 160,
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
            {clamped}
          </span>
          <span className="text-xs text-muted-foreground">{label}</span>
        </div>
      </div>
    </div>
  );
}
