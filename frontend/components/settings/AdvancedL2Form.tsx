"use client";

import * as React from "react";
import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import { useTranslations } from "next-intl";

export interface AdvancedL2FormProps {
  form: ReactNode;
  isSaving?: boolean;
  onSave: () => void;
  canReset?: boolean;
  onReset?: () => void;
  className?: string;
}

/**
 * Presentational shell for the Advanced L2 (drama enhancement) settings tab.
 */
export function AdvancedL2Form({
  form,
  isSaving = false,
  onSave,
  canReset = false,
  onReset,
  className,
}: AdvancedL2FormProps) {
  const t = useTranslations("settings_panel");

  return (
    <div className={cn("flex flex-col gap-4", className)}>
      <div
        role="note"
        className="flex items-start gap-2.5 rounded-lg border-l-2 border-accent bg-muted px-3 py-2.5 text-sm text-muted-foreground"
      >
        <AlertTriangle
          className="mt-0.5 size-4 shrink-0 text-foreground/70"
          aria-hidden
        />
        <p className="leading-relaxed">
          {t("form.l2.banner")}
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4 py-2">{form}</CardContent>
      </Card>

      <div className="sticky bottom-0 z-10 -mx-4 flex items-center justify-end gap-2 border-t bg-background/95 px-4 py-3 supports-backdrop-filter:backdrop-blur sm:mx-0 sm:rounded-lg sm:border sm:px-3 sm:py-2">
        {canReset ? (
          <Button
            type="button"
            variant="outline"
            onClick={onReset}
            disabled={isSaving}
          >
            {t("form.reset")}
          </Button>
        ) : null}
        <Button type="button" onClick={onSave} disabled={isSaving}>
          {isSaving ? t("form.saving") : t("form.save")}
        </Button>
      </div>
    </div>
  );
}
