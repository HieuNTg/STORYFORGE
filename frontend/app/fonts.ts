/**
 * StoryForge — next/font configuration.
 *
 * Cinema gold theme uses Playfair Display for the brand mark + section titles,
 * Inter for body/UI (full Vietnamese subset), JetBrains Mono for monospace
 * labels, and Source Serif 4 inside the Reader only.
 *
 * Variables exposed (consumed in globals.css @theme):
 *   --font-inter       → Inter (primary, --font-sans first)
 *   --font-geist-sans  → Geist Sans (latin-only fallback)
 *   --font-playfair    → Playfair Display (display serif, --font-display)
 *   --font-geist-mono  → Geist Mono (back-compat)
 *   --font-jetbrains   → JetBrains Mono (cinema mono accent)
 *   --font-source-serif → Source Serif 4 (reader only, lazy)
 *
 * All use `display: 'swap'` to avoid FOIT.
 */

import {
  Geist,
  Geist_Mono,
  Inter,
  JetBrains_Mono,
  Playfair_Display,
  Source_Serif_4,
} from "next/font/google";

export const fontSans = Inter({
  subsets: ["latin", "vietnamese"],
  display: "swap",
  variable: "--font-inter",
  preload: true,
});

export const fontGeist = Geist({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-geist-sans",
  preload: true,
});

export const fontMono = Geist_Mono({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-geist-mono",
  preload: false,
});

/**
 * Cinema display serif — used by brand mark, section titles, hero copy.
 * Latin + Vietnamese subsets so it survives VN diacritics in titles.
 */
export const fontDisplay = Playfair_Display({
  subsets: ["latin", "vietnamese"],
  display: "swap",
  variable: "--font-playfair",
  preload: true,
  weight: ["400", "500", "600", "700", "800"],
});

/**
 * Cinema mono accent — used by taglines, timestamps, tech labels.
 * Latin only is sufficient (no Vietnamese mono usage in design).
 */
export const fontMonoAccent = JetBrains_Mono({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-jetbrains",
  preload: false,
  weight: ["400", "500", "600"],
});

/**
 * Reader-only. Do NOT apply on root <html>. Reader page imports and adds:
 *   <article className={fontSerif.variable}>
 * Loading is deferred (preload:false) — pays the network only when reader opens.
 */
export const fontSerif = Source_Serif_4({
  subsets: ["latin", "vietnamese"],
  display: "swap",
  variable: "--font-source-serif",
  preload: false,
  weight: ["400", "500", "600", "700"],
});
