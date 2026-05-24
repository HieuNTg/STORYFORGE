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
import { CharacterList } from "./CharacterList";
import { CharacterDetail } from "./CharacterDetail";
import { CreateCharacterForm } from "./CreateCharacterForm";
import type { ForgeCharacter, Story } from "@/types/story";
import { extractStoryCharacters } from "@/lib/api/characters";
import { toast } from "sonner";
import { Sparkles, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export function CharactersScreen() {
  const t = useTranslations("characters");
  const stories = useLibraryStore((s) => s.stories);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const upsertCharacter = useLibraryStore((s) => s.upsertCharacter);
  const updateStory = useLibraryStore((s) => s.updateStory);

  const [storyId, setStoryId] = React.useState<string | null>(null);
  const [selectedName, setSelectedName] = React.useState<string | null>(null);

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

  const [isExtracting, setIsExtracting] = React.useState(false);

  const handleExtract = React.useCallback(async () => {
    if (!activeStory || isExtracting) return;
    setIsExtracting(true);
    try {
      const textContext = activeStory.chapters.map((c) => `${c.title}\n${c.summary || c.content}`).join("\n\n").slice(0, 10000);
      if (textContext.length < 50) {
        toast.error("Truyện quá ngắn để trích xuất.");
        setIsExtracting(false);
        return;
      }
      const chars = await extractStoryCharacters({
        title: activeStory.title,
        description: activeStory.description || "",
        setting: activeStory.setting || "",
        text_context: textContext,
      });
      if (chars.length === 0) {
        toast.error("AI không tìm thấy nhân vật nào.");
      } else {
        updateStory(activeStory.id, { characters: chars });
        setSelectedName(chars[0]?.name || null);
        toast.success(`Đã trích xuất ${chars.length} nhân vật.`);
      }
    } catch (err) {
      toast.error("Lỗi trích xuất nhân vật", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      setIsExtracting(false);
    }
  }, [activeStory, isExtracting, updateStory]);

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
    },
    [storyId, upsertCharacter],
  );

  const selectedChar = React.useMemo(
    () =>
      activeStory?.characters.find((c) => c.name === selectedName) ?? null,
    [activeStory, selectedName],
  );

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
          Truyện
        </label>
        <Select
          value={storyId ?? ""}
          onValueChange={(v) => setStoryId(v || null)}
        >
          <SelectTrigger className="w-[280px]" aria-label="Truyện">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {stories.map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.title}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[280px_1fr]">
        <div className="space-y-4">
          <CharacterList
            characters={activeStory?.characters ?? []}
            selectedName={selectedName}
            onSelect={setSelectedName}
          />
          <div className="rounded-xl border border-border/40 bg-card/40 p-4">
            <h3 className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {t("create")}
            </h3>
            <CreateCharacterForm
              defaultGenre={activeStory?.genre}
              onCreated={handleCreated}
            />
          </div>
        </div>

        {selectedChar ? (
          <CharacterDetail
            character={selectedChar}
            genre={activeStory?.genre}
          />
        ) : (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border/60 p-8 text-center text-sm text-muted-foreground">
            {activeStory?.chapters.length ? (
              <div className="space-y-4">
                <p>Truyện này đã có chương nhưng chưa có hồ sơ nhân vật.</p>
                <Button onClick={() => void handleExtract()} disabled={isExtracting}>
                  {isExtracting ? (
                    <Loader2 className="mr-2 size-4 animate-spin" />
                  ) : (
                    <Sparkles className="mr-2 size-4 text-[var(--accent)]" />
                  )}
                  {isExtracting ? "Đang đọc truyện và trích xuất..." : "Trích xuất nhân vật bằng AI"}
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
