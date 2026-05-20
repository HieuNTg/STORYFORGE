"use client";

/**
 * SimulationView — Phase 3 host.
 *
 * 3-col layout: Setup | Transcript theater | Controls.
 * Reads enable_simulation_transcript + enable_drama_climax from /api/config.
 * If disabled, renders an explainer instead of the workspace.
 */

import * as React from "react";
import { useTranslations } from "next-intl";
import { apiFetch } from "@/lib/api/client";
import { rehydrateLibrary } from "@/stores/library-store";
import { SetupPanel } from "./SetupPanel";
import { TranscriptTheater } from "./TranscriptTheater";
import { ControlsPanel } from "./ControlsPanel";

interface ConfigResponse {
  pipeline?: {
    enable_simulation_transcript?: boolean;
    enable_drama_climax?: boolean;
  };
}

export function SimulationView() {
  const t = useTranslations("simulation");
  const [flags, setFlags] = React.useState<{ enabled: boolean; climax: boolean } | null>(
    null,
  );

  React.useEffect(() => {
    rehydrateLibrary();
    let cancelled = false;
    apiFetch<ConfigResponse>("/api/config")
      .then((cfg) => {
        if (cancelled) return;
        setFlags({
          enabled: Boolean(cfg?.pipeline?.enable_simulation_transcript),
          climax: Boolean(cfg?.pipeline?.enable_drama_climax),
        });
      })
      .catch(() => {
        if (cancelled) return;
        setFlags({ enabled: false, climax: false });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (flags === null) {
    return (
      <p className="text-sm text-muted-foreground" role="status" aria-live="polite">
        …
      </p>
    );
  }

  if (!flags.enabled) {
    return (
      <div className="rounded-xl border border-dashed border-border/60 p-8 text-center text-sm text-muted-foreground">
        {t("disabled")}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_1fr_320px]">
      <SetupPanel climaxUnlocked={flags.climax} />
      <TranscriptTheater />
      <ControlsPanel />
    </div>
  );
}
