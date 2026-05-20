"use client";

/**
 * TraitRadar — 4-axis radar (strength/wisdom/agility/scheme).
 *
 * - recharts loaded dynamically (ssr:false; recharts has no SSR support).
 * - Axis labels resolved via next-intl `traits.*` + genre-aware Hán-Việt
 *   override for tiên-hiệp / wuxia.
 * - Includes accessible textual fallback for screen readers.
 */
import * as React from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { TRAIT_AXES, TRAIT_AXES_HAN_VIET, isHanVietGenre } from "@/lib/i18n/trait-axes";
import type { TraitKey, Traits } from "@/types/story";

const TraitRadarChart = dynamic(() => import("./TraitRadarChart"), {
  ssr: false,
  loading: () => (
    <div className="flex h-[220px] items-center justify-center text-xs text-muted-foreground">
      …
    </div>
  ),
});

export interface TraitRadarProps {
  traits: Traits;
  genre?: string | null;
  size?: number;
  /** When true, suppress recharts and only render textual summary. */
  textOnly?: boolean;
}

export function TraitRadar({ traits, genre, size, textOnly }: TraitRadarProps) {
  const tTraits = useTranslations("traits");

  const labels = React.useMemo<Record<TraitKey, string>>(() => {
    if (isHanVietGenre(genre)) {
      return { ...TRAIT_AXES_HAN_VIET };
    }
    return {
      strength: tTraits("strength"),
      wisdom: tTraits("wisdom"),
      agility: tTraits("agility"),
      scheme: tTraits("scheme"),
    };
  }, [genre, tTraits]);

  const summary = TRAIT_AXES.map((k) => `${labels[k]} ${traits[k]}`).join(" · ");

  return (
    <div className="space-y-2">
      {!textOnly ? (
        <TraitRadarChart
          traits={traits}
          axes={TRAIT_AXES}
          axisLabels={labels}
          size={size}
        />
      ) : null}
      <p
        className="text-center text-xs text-muted-foreground"
        aria-label={`Traits: ${summary}`}
      >
        {summary}
      </p>
    </div>
  );
}
