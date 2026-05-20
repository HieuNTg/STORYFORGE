"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
  const topic = useSimulationStore((s) => s.topic);
  const dramaLevel = useSimulationStore((s) => s.dramaLevel);
  const setTopic = useSimulationStore((s) => s.setTopic);
  const setDramaLevel = useSimulationStore((s) => s.setDramaLevel);
  const setCharacters = useSimulationStore((s) => s.setCharacters);
  const loadFromSession = useSimulationStore((s) => s.loadFromSession);
  const sessionId = useSimulationStore((s) => s.sessionId);

  const [storyId, setStoryId] = React.useState<string | null>(null);
  const [sessionInput, setSessionInput] = React.useState("");

  React.useEffect(() => {
    if (!storyId && stories.length) setStoryId(stories[0].id);
  }, [storyId, stories]);

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
        description: c.description,
      })),
    );
  }, [activeStory, setCharacters]);

  return (
    <aside className="space-y-5 rounded-xl border border-border/40 bg-card/40 p-4">
      <header>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          {t("setup")}
        </h3>
      </header>

      <div className="space-y-2">
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {t("characters_label")}
        </label>
        {stories.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("characters_pick_hint")}</p>
        ) : (
          <Select value={storyId ?? undefined} onValueChange={(v) => setStoryId(v)}>
            <SelectTrigger className="w-full">
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
        )}
        {activeStory && activeStory.characters.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t("characters_none")}</p>
        ) : null}
        {activeStory && activeStory.characters.length > 0 ? (
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
        ) : null}
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
