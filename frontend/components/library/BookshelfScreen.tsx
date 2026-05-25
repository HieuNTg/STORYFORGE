"use client";

/**
 * BookshelfScreen — Phase 1 host: toolbar + ForgePanel + BookshelfGrid +
 * CreateStoryModal + StoryWorkspace. All state is client-side (zustand store
 * `useLibraryStore`).
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Plus, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ForgePanel } from "./ForgePanel";
import { BookshelfGrid } from "./BookshelfGrid";
import { CreateStoryModal } from "./CreateStoryModal";
import { StoryWorkspace } from "./StoryWorkspace";
import {
  useLibraryStore,
  rehydrateLibrary,
  LIBRARY_MAX_STORIES,
} from "@/stores/library-store";
import { importStory } from "@/lib/library/json-io";
import { forgeToStory } from "@/lib/library/story-mappers";
import type { ForgeResponse, Story } from "@/types/story";

export function BookshelfScreen() {
  const router = useRouter();
  const t = useTranslations("library");
  const stories = useLibraryStore((s) => s.stories);
  const selectedId = useLibraryStore((s) => s.selectedId);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const addStory = useLibraryStore((s) => s.addStory);
  const removeStory = useLibraryStore((s) => s.removeStory);
  const selectStory = useLibraryStore((s) => s.selectStory);

  const handleOpenReader = React.useCallback(
    (id: string) => {
      selectStory(id);
      router.push(`/reader/?id=${encodeURIComponent(id)}`);
    },
    [router, selectStory],
  );

  const handleOpenContinue = React.useCallback(
    (id: string) => {
      selectStory(id);
      router.push(`/continue/?id=${encodeURIComponent(id)}`);
    },
    [router, selectStory],
  );

  const [createOpen, setCreateOpen] = React.useState(false);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    rehydrateLibrary();
  }, []);

  const handleForged = React.useCallback(
    (forge: ForgeResponse) => {
      const story = forgeToStory(forge);
      const ok = addStory(story);
      if (!ok) {
        toast.error(`Đã đạt giới hạn ${LIBRARY_MAX_STORIES} truyện`);
      }
    },
    [addStory],
  );

  const handleManualCreate = React.useCallback(
    (story: Story) => {
      const ok = addStory(story);
      if (!ok) {
        toast.error(`Đã đạt giới hạn ${LIBRARY_MAX_STORIES} truyện`);
      }
    },
    [addStory],
  );

  const handleImportClick = () => fileInputRef.current?.click();

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const story = await importStory(file);
      const ok = addStory(story);
      if (!ok) {
        toast.error(t("limit_reached", { max: LIBRARY_MAX_STORIES }));
        return;
      }
      toast.success(t("imported"), { description: story.title });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const friendly =
        msg === "file_too_large"
          ? t("file_too_large")
          : msg === "invalid_json"
            ? t("invalid_json")
            : msg;
      toast.error(t("import_failed"), { description: friendly });
    }
  };

  const selectedStory = React.useMemo(
    () => (selectedId ? stories.find((s) => s.id === selectedId) ?? null : null),
    [selectedId, stories],
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">
          {hydrated
            ? t("count", { count: stories.length, max: LIBRARY_MAX_STORIES })
            : t("loading_shelf")}
        </p>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="sr-only"
            onChange={handleImportFile}
            tabIndex={-1}
            aria-label={t("import_file_label")}
          />
          <Button
            type="button"
            variant="outline"
            onClick={handleImportClick}
            className="gap-1.5"
          >
            <Upload className="size-4" aria-hidden />
            {t("import")}
          </Button>
          <Button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="gap-1.5"
          >
            <Plus className="size-4" aria-hidden />
            {t("create")}
          </Button>
        </div>
      </div>

      <ForgePanel onForged={handleForged} />

      {stories.length === 0 ? (
        <BookshelfGrid
          stories={stories}
          selectedId={selectedId}
          onSelect={handleOpenReader}
          onCreate={() => setCreateOpen(true)}
        />
      ) : selectedStory ? (
        <StoryWorkspace
          story={selectedStory}
          onDelete={removeStory}
          onOpenReader={handleOpenReader}
          onOpenContinue={handleOpenContinue}
          className="max-w-sm"
        />
      ) : null}

      <CreateStoryModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreate={handleManualCreate}
      />
    </div>
  );
}

