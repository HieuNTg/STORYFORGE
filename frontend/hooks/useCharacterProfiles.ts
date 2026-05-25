"use client";

/**
 * useCharacterProfiles — fetches visual profiles for all characters in a story.
 *
 * Wraps GET /api/images/{session_id}/profiles. Returns a Map keyed by character
 * name so callers can do O(1) lookup for avatar URL + has_reference_image flag
 * in list rows.
 *
 * Silent fail by design: if backend errors (404 for unstored sessions, network
 * blip), we return an empty map and let the UI degrade to initial-letter
 * fallbacks. No toast — the sidebar must always render.
 */

import { useQuery } from "@tanstack/react-query";
import {
  listCharacterProfiles,
  type CharacterProfile,
} from "@/lib/api/illustration";

export interface UseCharacterProfilesResult {
  profiles: Map<string, CharacterProfile>;
  isLoading: boolean;
}

export function useCharacterProfiles(
  sessionId: string | null,
): UseCharacterProfilesResult {
  const query = useQuery({
    queryKey: ["character-profiles", sessionId],
    queryFn: async () => {
      if (!sessionId) return { profiles: [] };
      return listCharacterProfiles(sessionId);
    },
    enabled: !!sessionId,
    staleTime: 30_000,
    retry: false,
  });

  const profiles = new Map<string, CharacterProfile>();
  if (query.data) {
    for (const p of query.data.profiles) profiles.set(p.name, p);
  }

  return { profiles, isLoading: query.isLoading };
}
