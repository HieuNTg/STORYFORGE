/**
 * Genre-aware short trait axis labels.
 *
 * Locked: 4 fixed axes (strength/wisdom/agility/scheme).
 * Per-locale labels live in `messages/{locale}.json` under `traits.*`.
 * This module ONLY provides an optional genre-level override map for
 * tiên-hiệp/wuxia styling — keys still match the 4 axes.
 */
import type { TraitKey } from "@/types/story";

export const TRAIT_AXES: readonly TraitKey[] = [
  "strength",
  "wisdom",
  "agility",
  "scheme",
] as const;

/**
 * Optional Hán-Việt short labels for tiên-hiệp / wuxia genres.
 * Use these instead of `traits.{key}` when genre matches.
 */
export const TRAIT_AXES_HAN_VIET: Record<TraitKey, string> = {
  strength: "Lực",
  wisdom: "Trí",
  agility: "Khí",
  scheme: "Mưu",
};

const HAN_VIET_GENRES = new Set([
  "Tiên Hiệp",
  "Huyền Huyễn",
  "wuxia",
  "xianxia",
]);

export function isHanVietGenre(genre: string | null | undefined): boolean {
  if (!genre) return false;
  return HAN_VIET_GENRES.has(genre);
}
