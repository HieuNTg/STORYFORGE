/**
 * Cinema palette — raw hex constants for JS-side consumers (recharts, canvas, SVG).
 * Mirrors CSS tokens in `app/globals.css`. Keep in sync.
 */

export const GOLD = "#C5A47E" as const;
export const GOLD_BG_DARK = "#080808" as const;
export const GOLD_SURFACE_DARK = "#121212" as const;
export const GOLD_BG_LIGHT = "#F4EBE1" as const;
export const GOLD_SURFACE_LIGHT = "#EDE2D4" as const;

export const FG_DARK = "#E0E0E0" as const;
export const FG_LIGHT = "#1A1208" as const;

/** 5-token chart palette — keep in sync with --chart-1..5 in globals.css. */
export const CHART_PALETTE_DARK = [
  "#C5A47E",
  "#D9AA5A",
  "#8A6A4A",
  "#C97070",
  "#7AA57A",
] as const;

export const CHART_PALETTE_LIGHT = [
  "#C5A47E",
  "#79633F",
  "#B58A3A",
  "#8A4A4A",
  "#4F7A4A",
] as const;
