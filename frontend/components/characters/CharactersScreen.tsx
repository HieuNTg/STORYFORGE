"use client";

/**
 * CharactersScreen — Phase 2 host.
 *
 * Story picker (from library) → CharacterList + CharacterDetail panes +
 * CreateCharacterForm. New characters call /api/characters/generate and
 * upsert into the selected story via the library store.
 */

import * as React from "react";
import { useTranslations } from "next-intl";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useLibraryStore, rehydrateLibrary } from "@/stores/library-store";
import { CharacterList, type CharacterListItemMeta } from "./CharacterList";
import { CharacterDetail } from "./CharacterDetail";
import { CreateCharacterForm } from "./CreateCharacterForm";
import type { ForgeCharacter, Story } from "@/types/story";
import {
  extractStoryCharacters,
  generateAllCharacterAvatars,
  waitForAllAvatars,
} from "@/lib/api/characters";
import { displayStoryTitle } from "@/lib/library/display-helpers";
import { useCharacterProfiles } from "@/hooks/useCharacterProfiles";
import { useStoryAvatars } from "@/hooks/useStoryAvatars";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Sparkles, Loader2, Plus, Search, Images } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

function normalizeForSearch(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase()
    .trim();
}

export function CharactersScreen() {
  const t = useTranslations("characters");
  const tLib = useTranslations("library");
  const stories = useLibraryStore((s) => s.stories);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const upsertCharacter = useLibraryStore((s) => s.upsertCharacter);
  const removeCharacter = useLibraryStore((s) => s.removeCharacter);
  const updateStory = useLibraryStore((s) => s.updateStory);
  const queryClient = useQueryClient();

  const [storyId, setStoryId] = React.useState<string | null>(null);
  const [selectedName, setSelectedName] = React.useState<string | null>(null);
  const [searchQuery, setSearchQuery] = React.useState("");

  React.useEffect(() => {
    rehydrateLibrary();
  }, []);

  React.useEffect(() => {
    if (!storyId && stories.length) setStoryId(stories[0].id);
  }, [storyId, stories]);

  const activeStory = React.useMemo(
    () => stories.find((s) => s.id === storyId) ?? null,
    [storyId, stories],
  );

  const { profiles } = useCharacterProfiles(storyId);

  const characterNames = React.useMemo(
    () => (activeStory?.characters ?? []).map((c) => c.name),
    [activeStory],
  );
  // On-disk, story-scoped portraits — the source of truth for localStorage-only
  // library stories that aren't in the backend store (so `profiles` is empty).
  const { avatars } = useStoryAvatars(storyId, characterNames);

  const profilesByName = React.useMemo(() => {
    const map = new Map<string, CharacterListItemMeta>();
    // Pipeline-run stories (in the backend store): profile carries the
    // reference image + frozen-prompt flag.
    profiles.forEach((p, name) => {
      map.set(name, {
        avatarUrl: p.reference_url ?? null,
        hasReferenceImage: !!p.has_reference_image,
      });
    });
    // Overlay the story-scoped avatar files. For library stories this is the
    // only source; for stored stories it backfills a portrait when the profile
    // has none yet.
    avatars.forEach((url, name) => {
      const existing = map.get(name);
      if (existing) {
        if (!existing.avatarUrl) existing.avatarUrl = url;
      } else {
        map.set(name, { avatarUrl: url, hasReferenceImage: false });
      }
    });
    return map;
  }, [profiles, avatars]);

  const [isExtracting, setIsExtracting] = React.useState(false);
  const [createOpen, setCreateOpen] = React.useState(false);
  const handleExtract = React.useCallback(async () => {
    if (!activeStory || isExtracting) return;
    setIsExtracting(true);
    try {
      const textContext = activeStory.chapters.map((c) => `${c.title}\n${c.summary || c.content}`).join("\n\n").slice(0, 10000);
      if (textContext.length < 50) {
        toast.error(t("too_short"));
        setIsExtracting(false);
        return;
      }
      const chars = await extractStoryCharacters({
        title: activeStory.title,
        description: activeStory.description || "",
        setting: activeStory.setting || "",
        text_context: textContext,
        // Drive output language from the source story so a Vietnamese story
        // doesn't get characters with English bios. Default "vi" matches
        // CLAUDE.md primary audience.
        language: activeStory.language || "vi",
        // Scope avatars to this story so two unrelated stories with same-named
        // characters don't write into the same file. Genre drives the avatar
        // style anchor so a sci-fi character isn't returned in hanfu.
        story_id: activeStory.id,
        genre: activeStory.genre || undefined,
      });
      if (chars.length === 0) {
        toast.error(t("no_characters_found"));
      } else {
        updateStory(activeStory.id, { characters: chars });
        setSelectedName(chars[0]?.name || null);
        toast.success(t("extract_success", { count: chars.length }));
      }
    } catch (err) {
      toast.error(t("extract_failed"), {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsExtracting(false);
    }
  }, [activeStory, isExtracting, updateStory, t]);

  React.useEffect(() => {
    if (!activeStory) {
      setSelectedName(null);
      return;
    }
    if (selectedName && activeStory.characters.some((c) => c.name === selectedName)) return;
    setSelectedName(activeStory.characters[0]?.name ?? null);
  }, [activeStory, selectedName]);

  const handleCreated = React.useCallback(
    (character: ForgeCharacter) => {
      if (!storyId) return;
      upsertCharacter(storyId, character);
      setSelectedName(character.name);
      setCreateOpen(false);
    },
    [storyId, upsertCharacter],
  );

  const selectedChar = React.useMemo(
    () =>
      activeStory?.characters.find((c) => c.name === selectedName) ?? null,
    [activeStory, selectedName],
  );

  const visibleCharacters = React.useMemo(() => {
    const all = activeStory?.characters ?? [];
    const q = normalizeForSearch(searchQuery);
    if (!q) return all;
    return all.filter((c) => normalizeForSearch(c.name).includes(q));
  }, [activeStory, searchQuery]);

  const showSearch = (activeStory?.characters.length ?? 0) >= 5;

  const handleDeleteCharacter = React.useCallback(
    (name: string) => {
      if (!storyId) return;
      removeCharacter(storyId, name);
      const remaining = (activeStory?.characters ?? []).filter(
        (c) => c.name !== name,
      );
      setSelectedName(remaining[0]?.name ?? null);
      toast.success(t("delete_confirm_action"));
    },
    [storyId, removeCharacter, activeStory, t],
  );

  const handleAvatarRegenerated = React.useCallback(() => {
    if (!storyId) return;
    void queryClient.invalidateQueries({
      queryKey: ["character-profiles", storyId],
    });
    // Refetch the on-disk avatar map too — regeneration changes the file's
    // mtime, so the lookup returns a new ?v= URL that reloads the <img>.
    void queryClient.invalidateQueries({
      queryKey: ["story-avatars", storyId],
    });
  }, [queryClient, storyId]);

  // Bulk avatar generation: queue every character on the backend (fire-and-
  // forget — FlowKit serializes ~25-30s/portrait, so holding one request for
  // all of them would trip the dev proxy), then poll until each file lands,
  // surfacing portraits on the list as they arrive.
  const [isGeneratingAll, setIsGeneratingAll] = React.useState(false);
  const [genDone, setGenDone] = React.useState(0);

  const handleGenerateAll = React.useCallback(async () => {
    if (!activeStory || !storyId || isGeneratingAll) return;
    const chars = activeStory.characters ?? [];
    if (chars.length === 0) return;
    const names = chars.map((c) => c.name);
    setIsGeneratingAll(true);
    setGenDone(0);
    try {
      await generateAllCharacterAvatars(
        chars,
        storyId,
        activeStory.genre || undefined,
      );
      const final = await waitForAllAvatars(storyId, names, {
        onTick: (avatars) => {
          setGenDone(names.filter((n) => avatars[n]).length);
          // Reveal portraits incrementally as the background task writes them.
          void queryClient.invalidateQueries({
            queryKey: ["story-avatars", storyId],
          });
        },
      });
      void queryClient.invalidateQueries({ queryKey: ["story-avatars", storyId] });
      const done = names.filter((n) => final[n]).length;
      if (done >= names.length) {
        toast.success(t("generate_all_success", { count: done }));
      } else {
        toast.warning(t("generate_all_partial", { done, total: names.length }));
      }
    } catch (err) {
      toast.error(t("generate_all_failed"), {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsGeneratingAll(false);
    }
  }, [activeStory, storyId, isGeneratingAll, queryClient, t]);

  if (!hydrated) {
    return (
      <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
        {t("loading")}
      </p>
    );
  }

  if (!stories.length) {
    return (
      <div className="rounded-xl border border-dashed border-border/60 p-8 text-center text-sm text-muted-foreground">
        <p className="font-medium">{t("empty")}</p>
        <p className="mt-1 text-xs">{t("empty_hint")}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {t("label_story")}
        </label>
        <Select
          value={storyId ?? ""}
          onValueChange={(v) => setStoryId(v || null)}
        >
          <SelectTrigger className="w-[280px]" aria-label={t("label_story")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {stories.map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {displayStoryTitle(s, tLib("untitled_story"))}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2 px-1">
            <h3 className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
              {t("list_heading")} · {activeStory?.characters.length ?? 0}
            </h3>
            <div className="flex items-center gap-1">
              {(activeStory?.characters.length ?? 0) > 0 ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs text-[var(--accent)] hover:text-[var(--accent)]"
                  onClick={() => void handleGenerateAll()}
                  disabled={!storyId || isGeneratingAll}
                  title={t("generate_all_avatars")}
                >
                  {isGeneratingAll ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <Images className="size-3.5" />
                  )}
                  {isGeneratingAll
                    ? t("generating_all_avatars", {
                        done: genDone,
                        total: activeStory?.characters.length ?? 0,
                      })
                    : t("generate_all_avatars")}
                </Button>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 px-2 text-xs text-[var(--accent)] hover:text-[var(--accent)]"
                onClick={() => setCreateOpen(true)}
                disabled={!storyId}
              >
                <Plus className="size-3.5" />
                {t("create_open")}
              </Button>
            </div>
          </div>
          {showSearch ? (
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                type="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={t("search_placeholder")}
                className="h-8 pl-8 text-xs"
                aria-label={t("search_placeholder")}
              />
            </div>
          ) : null}
          {searchQuery && visibleCharacters.length === 0 ? (
            <p className="px-2 py-3 text-xs text-muted-foreground">
              {t("no_results")}
            </p>
          ) : (
            <CharacterList
              characters={visibleCharacters}
              selectedName={selectedName}
              onSelect={setSelectedName}
              profilesByName={profilesByName}
            />
          )}
        </div>

        <Sheet open={createOpen} onOpenChange={setCreateOpen}>
          <SheetContent
            side="right"
            className="flex w-full flex-col gap-0 sm:max-w-md"
          >
            <SheetHeader>
              <SheetTitle>{t("create_sheet_title")}</SheetTitle>
              <SheetDescription>
                {t("create_sheet_description")}
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 overflow-y-auto px-4 pb-4">
              <CreateCharacterForm
                defaultGenre={activeStory?.genre}
                language={activeStory?.language || "vi"}
                onCreated={handleCreated}
              />
            </div>
          </SheetContent>
        </Sheet>

        {selectedChar ? (
          <CharacterDetail
            character={selectedChar}
            genre={activeStory?.genre}
            portraitUrl={profilesByName.get(selectedChar.name)?.avatarUrl ?? null}
            sessionId={storyId}
            onAvatarRegenerated={handleAvatarRegenerated}
            onDelete={handleDeleteCharacter}
          />
        ) : (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/60 p-8 text-center text-sm text-muted-foreground">
            {activeStory?.chapters.length ? (
              <div className="space-y-4">
                <p>{t("draft_no_characters")}</p>
                <Button onClick={() => void handleExtract()} disabled={isExtracting}>
                  {isExtracting ? (
                    <Loader2 className="mr-2 size-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 size-4 text-[var(--accent)]" />
                  )}
                  {isExtracting ? t("extracting_status") : t("extract_cta")}
                </Button>
              </div>
            ) : (
              <p>{t("empty_hint")}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
