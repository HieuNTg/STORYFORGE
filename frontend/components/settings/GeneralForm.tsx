"use client";

import * as React from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export interface GeneralFormProps {
  form: ReactNode;
  isSaving?: boolean;
  onSave: () => void;
  canReset?: boolean;
  onReset?: () => void;
  className?: string;
}

/**
 * Presentational shell for the General settings tab.
 * Wraps form fields in a Card with a sticky save bar at the bottom.
 */
export function GeneralForm({
  form,
  isSaving = false,
  onSave,
  canReset = false,
  onReset,
  className,
}: GeneralFormProps) {
  return (
    <div className={cn("flex flex-col gap-4", className)}>
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
            Đặt lại
          </Button>
        ) : null}
        <Button type="button" onClick={onSave} disabled={isSaving}>
          {isSaving ? "Đang lưu..." : "Lưu"}
        </Button>
      </div>
    </div>
  );
}
