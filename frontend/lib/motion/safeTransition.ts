import type { Transition, Variants } from "motion/react";

/**
 * Bounded transition presets shared across the app. Single source of truth so
 * Phase 6 motion stays consistent and `prefers-reduced-motion` opt-outs are
 * easy to wire (consumers branch on `useReducedMotion()` and skip the variant).
 *
 * Rule: never set `repeat: Infinity` here. Every transition is finite.
 */

export const fadeIn: Variants = {
  hidden: { opacity: 0, y: 6 },
  visible: { opacity: 1, y: 0 },
};

export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  visible: { opacity: 1, scale: 1 },
};

export const staggerChildren: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { staggerChildren: 0.05, delayChildren: 0.04 },
  },
};

export const hoverLift: Transition = {
  type: "spring",
  stiffness: 320,
  damping: 22,
  mass: 0.4,
};

export const smooth: Transition = {
  duration: 0.32,
  ease: [0.22, 1, 0.36, 1],
};

export const crossfade: Transition = {
  duration: 0.22,
  ease: "easeOut",
};

/**
 * Returns the supplied variants when motion is allowed, otherwise a no-op
 * pair that resolves to the visible state immediately. Use in components
 * that wrap their own `useReducedMotion()` check:
 *
 *   const reduce = useReducedMotion();
 *   <motion.div variants={safeVariants(scaleIn, reduce)} ... />
 */
export function safeVariants(variants: Variants, reduce: boolean | null): Variants {
  if (!reduce) return variants;
  return { hidden: { opacity: 1 }, visible: { opacity: 1 } };
}
