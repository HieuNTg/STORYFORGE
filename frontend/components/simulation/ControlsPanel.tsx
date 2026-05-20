"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useSimulationStore } from "@/stores/simulation-store";

interface ControlsPanelProps {
  onForgeOutline?: () => void;
}

export function ControlsPanel({ onForgeOutline }: ControlsPanelProps) {
  const t = useTranslations("simulation");
  const logs = useSimulationStore((s) => s.logs);
  const cursor = useSimulationStore((s) => s.cursor);
  const playing = useSimulationStore((s) => s.playing);
  const busy = useSimulationStore((s) => s.busy);
  const error = useSimulationStore((s) => s.error);
  const outcomeSummary = useSimulationStore((s) => s.outcomeSummary);
  const stepForward = useSimulationStore((s) => s.stepForward);
  const stepBackward = useSimulationStore((s) => s.stepBackward);
  const play = useSimulationStore((s) => s.play);
  const pause = useSimulationStore((s) => s.pause);
  const continueAI = useSimulationStore((s) => s.continueAI);
  const injectTurn = useSimulationStore((s) => s.injectTurn);

  const [sender, setSender] = React.useState("");
  const [emotion, setEmotion] = React.useState("");
  const [action, setAction] = React.useState("");
  const [speech, setSpeech] = React.useState("");

  const handleInject = () => {
    if (!sender.trim()) return;
    injectTurn({
      senderId: sender.trim(),
      senderName: sender.trim(),
      emotion: emotion.trim(),
      actionDetails: action.trim(),
      speech: speech.trim(),
    });
    setEmotion("");
    setAction("");
    setSpeech("");
  };

  const noLogs = logs.length === 0;

  return (
    <aside className="space-y-5 rounded-xl border border-border/40 bg-card/40 p-4">
      <div className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          {t("transcript")}
        </h3>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={stepBackward}
            disabled={noLogs || cursor <= 0}
          >
            ◂ {t("step_back")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={stepForward}
            disabled={noLogs || cursor >= logs.length - 1}
          >
            {t("step_forward")} ▸
          </Button>
          {playing ? (
            <Button type="button" size="sm" variant="secondary" onClick={pause}>
              ⏸ {t("pause")}
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={play}
              disabled={noLogs || cursor >= logs.length - 1}
            >
              ▶ {t("play")}
            </Button>
          )}
        </div>
        <Button
          type="button"
          size="sm"
          className="w-full"
          onClick={continueAI}
          disabled={busy}
        >
          {busy ? t("continue_busy") : t("continue_ai")}
        </Button>
        {error ? (
          <p className="text-xs text-destructive" role="alert">
            {t("error_generic", { msg: error })}
          </p>
        ) : null}
      </div>

      <div className="space-y-2 border-t border-border/40 pt-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          {t("inject_title")}
        </h3>
        <Input
          value={sender}
          onChange={(e) => setSender(e.target.value)}
          placeholder={t("inject_sender")}
          maxLength={80}
        />
        <Input
          value={emotion}
          onChange={(e) => setEmotion(e.target.value)}
          placeholder={t("inject_emotion")}
          maxLength={80}
        />
        <Input
          value={action}
          onChange={(e) => setAction(e.target.value)}
          placeholder={t("inject_action")}
          maxLength={500}
        />
        <Textarea
          value={speech}
          onChange={(e) => setSpeech(e.target.value)}
          placeholder={t("inject_speech")}
          rows={3}
          maxLength={500}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="w-full"
          onClick={handleInject}
          disabled={!sender.trim()}
        >
          {t("inject_submit")}
        </Button>
      </div>

      <div className="space-y-2 border-t border-border/40 pt-4">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          {t("outcome")}
        </h3>
        {outcomeSummary ? (
          <p className="whitespace-pre-line text-xs leading-relaxed text-muted-foreground">
            {outcomeSummary}
          </p>
        ) : (
          <p className="text-xs text-muted-foreground">{t("outcome_empty")}</p>
        )}
        {onForgeOutline ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="w-full"
            onClick={onForgeOutline}
            disabled={noLogs}
          >
            {t("forge_outline_cta")}
          </Button>
        ) : null}
      </div>
    </aside>
  );
}
