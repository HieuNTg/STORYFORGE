"use client";

import * as React from "react";
import { PortraitPanel } from "./PortraitPanel";
import { TraitRadar } from "./TraitRadar";
import { NarrativePanels } from "./NarrativePanels";
import { RoleBadge } from "./RoleBadge";
import type { ForgeCharacter } from "@/types/story";

export interface CharacterDetailProps {
  character: ForgeCharacter;
  genre?: string | null;
  portraitUrl?: string | null;
}

export function CharacterDetail({
  character,
  genre,
  portraitUrl,
}: CharacterDetailProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-[1fr_1.4fr]">
      <div className="space-y-3">
        <PortraitPanel name={character.name} src={portraitUrl} />
        <div className="flex items-center justify-between gap-2">
          <h3 className="truncate text-lg font-semibold">{character.name}</h3>
          <RoleBadge role={character.role} />
        </div>
        <div className="rounded-xl border border-border/40 bg-card/40 p-3">
          <TraitRadar traits={character.traits} genre={genre} />
        </div>
      </div>
      <NarrativePanels character={character} />
    </div>
  );
}
