"use client";

/**
 * BookshelfScreen — Phase 1 host: toolbar + ForgePanel + BookshelfGrid +
 * CreateStoryModal + StoryWorkspace. All state is client-side (zustand store
 * `useLibraryStore`).
 */

import * as React from "react";
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
  const stories = useLibraryStore((s) => s.stories);
  const selectedId = useLibraryStore((s) => s.selectedId);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const addStory = useLibraryStore((s) => s.addStory);
  const removeStory = useLibraryStore((s) => s.removeStory);
  const selectStory = useLibraryStore((s) => s.selectStory);

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
        toast.error(`Đã đạt giới hạn ${LIBRARY_MAX_STORIES} truyện`);
        return;
      }
      toast.success("Đã nhập truyện", { description: story.title });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      const friendly =
        msg === "file_too_large"
          ? "Tệp quá lớn (>1MB)"
          : msg === "invalid_json"
            ? "Tệp JSON không hợp lệ"
            : msg;
      toast.error("Nhập thất bại", { description: friendly });
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
            ? `${stories.length} / ${LIBRARY_MAX_STORIES} truyện trong kho`
            : "Đang tải kho truyện…"}
        </p>
        <div className="flex gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json,.json"
            className="sr-only"
            onChange={handleImportFile}
            tabIndex={-1}
            aria-label="Chọn tệp JSON để nhập vào kho truyện"
          />
          <Button
            type="button"
            variant="outline"
            onClick={handleImportClick}
            className="gap-1.5"
          >
            <Upload className="size-4" aria-hidden />
            Nhập JSON
          </Button>
          <Button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="gap-1.5"
          >
            <Plus className="size-4" aria-hidden />
            Tạo truyện
          </Button>
        </div>
      </div>

      <ForgePanel onForged={handleForged} />

      {stories.length === 0 ? (
        <BookshelfGrid
          stories={stories}
          selectedId={selectedId}
          onSelect={selectStory}
          onCreate={() => setCreateOpen(true)}
        />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
          <BookshelfGrid
            stories={stories}
            selectedId={selectedId}
            onSelect={selectStory}
          />
          {selectedStory ? (
            <StoryWorkspace story={selectedStory} onDelete={removeStory} />
          ) : null}
        </div>
      )}

      <CreateStoryModal
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreate={handleManualCreate}
      />
    </div>
  );
}
