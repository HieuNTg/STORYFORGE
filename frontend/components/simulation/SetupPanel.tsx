"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { useLibraryStore } from "@/stores/library-store";
import { useSimulationStore } from "@/stores/simulation-store";
import type { DramaLevel } from "@/types/story";

const DRAMA_LEVELS: DramaLevel[] = ["low", "medium", "high", "climax"];

interface SetupPanelProps {
  climaxUnlocked?: boolean;
}

export function SetupPanel({ climaxUnlocked = false }: SetupPanelProps) {
  const t = useTranslations("simulation");
  const stories = useLibraryStore((s) => s.stories);
  const selectedId = useLibraryStore((s) => s.selectedId);
  const hydrated = useLibraryStore((s) => s.hydrated);
  const topic = useSimulationStore((s) => s.topic);
  const dramaLevel = useSimulationStore((s) => s.dramaLevel);
  const setTopic = useSimulationStore((s) => s.setTopic);
  const setDramaLevel = useSimulationStore((s) => s.setDramaLevel);
  const setCharacters = useSimulationStore((s) => s.setCharacters);
  const loadFromSession = useSimulationStore((s) => s.loadFromSession);
  const sessionId = useSimulationStore((s) => s.sessionId);

  const [storyId, setStoryId] = React.useState("");
  const [sessionInput, setSessionInput] = React.useState("");

  React.useEffect(() => {
    if (!hydrated || storyId) return;
    if (selectedId && stories.some((s) => s.id === selectedId)) {
      setStoryId(selectedId);
      return;
    }
    if (stories.length > 0) setStoryId(stories[0].id);
  }, [hydrated, selectedId, stories, storyId]);

  const activeStory = React.useMemo(
    () => stories.find((s) => s.id === storyId) ?? null,
    [storyId, stories],
  );

  React.useEffect(() => {
    if (!activeStory) {
      setCharacters([]);
      return;
    }
    setCharacters(
      activeStory.characters.map((c) => ({
        name: c.name,
        role: c.role,
        description: c.description || c.backstory || "",
      })),
    );
    if (!topic.trim() && activeStory.description) {
      setTopic(activeStory.description);
    }
  }, [activeStory, setCharacters, setTopic, topic]);

  return (
    <aside className="space-y-5 rounded-xl border border-border/40 bg-card/40 p-4">
      <header>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          {t("setup")}
        </h3>
      </header>

      <div className="space-y-2">
        <label htmlFor="sim-story" className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Bộ truyện
        </label>
        {!hydrated ? (
          <p className="text-xs text-muted-foreground">Đang tải kho truyện…</p>
        ) : stories.length === 0 ? (
          <p className="text-xs text-muted-foreground">Tạo hoặc nhập một bộ truyện trong Thư viện trước.</p>
        ) : (
          <select
            id="sim-story"
            value={storyId}
            onChange={(e) => setStoryId(e.target.value)}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {stories.map((s) => (
              <option key={s.id} value={s.id}>
                {s.title}
              </option>
            ))}
          </select>
        )}
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Nhân vật trong cảnh
        </label>
        {!activeStory ? (
          <p className="text-xs text-muted-foreground">Chọn truyện để tải nhân vật.</p>
        ) : activeStory.characters.length === 0 ? (
          <p className="text-xs text-muted-foreground">Truyện này chưa có nhân vật.</p>
        ) : (
          <ul className="flex flex-wrap gap-1.5">
            {activeStory.characters.map((c) => (
              <li
                key={c.name}
                className="rounded-full border border-border/60 bg-background/60 px-2 py-0.5 text-xs"
              >
                {c.name}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="space-y-2">
        <label
          htmlFor="sim-topic"
          className="text-xs font-medium uppercase tracking-wider text-muted-foreground"
        >
          {t("topic_label")}
        </label>
        <Textarea
          id="sim-topic"
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder={t("topic_placeholder")}
          rows={4}
          maxLength={2000}
        />
      </div>

      <div className="space-y-2">
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {t("drama_label")}
        </label>
        <div className="grid grid-cols-2 gap-2">
          {DRAMA_LEVELS.map((lvl) => {
            const locked = lvl === "climax" && !climaxUnlocked;
            const selected = dramaLevel === lvl;
            return (
              <Button
                key={lvl}
                type="button"
                variant={selected ? "default" : "outline"}
                size="sm"
                disabled={locked}
                title={locked ? t("drama_climax_locked") : undefined}
                onClick={() => setDramaLevel(lvl)}
              >
                {t(`drama_${lvl}` as const)}
              </Button>
            );
          })}
        </div>
      </div>

      <div className="space-y-2 border-t border-border/40 pt-4">
        <label
          htmlFor="sim-session"
          className="text-xs font-medium uppercase tracking-wider text-muted-foreground"
        >
          {t("load_session")}
        </label>
        <div className="flex gap-2">
          <input
            id="sim-session"
            value={sessionInput}
            onChange={(e) => setSessionInput(e.target.value)}
            placeholder={t("load_session_placeholder")}
            className="flex-1 rounded-md border border-border/60 bg-background/60 px-2 py-1.5 text-xs"
            maxLength={64}
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!sessionInput.trim()}
            onClick={() => loadFromSession(sessionInput.trim())}
          >
            {t("load_session_cta")}
          </Button>
        </div>
        {sessionId ? (
          <p className="text-[11px] text-muted-foreground">→ {sessionId}</p>
        ) : null}
      </div>
    </aside>
  );
}
