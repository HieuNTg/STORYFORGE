"use client";

import * as React from "react";
import type { ReactNode } from "react";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

export interface SettingsWizardStep {
  id: string;
  title: string;
  description: string;
  content: ReactNode;
}

export interface SettingsWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  steps: SettingsWizardStep[];
  currentStep: number;
  onNext: () => void;
  onPrev: () => void;
  onFinish: () => void;
  canNext?: boolean;
  isFinishing?: boolean;
  className?: string;
}

/**
 * First-time setup wizard. 3-step stepper with dot indicators, completed
 * checkmarks, and dismissible close. Tab-trap is handled by the Dialog primitive.
 */
export function SettingsWizard({
  open,
  onOpenChange,
  steps,
  currentStep,
  onNext,
  onPrev,
  onFinish,
  canNext = true,
  isFinishing = false,
  className,
}: SettingsWizardProps) {
  const total = steps.length;
  const safeIndex = Math.max(0, Math.min(total - 1, currentStep));
  const active = steps[safeIndex];
  const isFirst = safeIndex === 0;
  const isLast = safeIndex === total - 1;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className={cn("sm:max-w-lg gap-0 p-0", className)}
      >
        <DialogHeader className="px-5 pt-5 pb-3">
          <Stepper steps={steps} currentIndex={safeIndex} />
          <DialogTitle className="mt-4 text-lg">
            {active?.title ?? ""}
          </DialogTitle>
          <DialogDescription>{active?.description ?? ""}</DialogDescription>
        </DialogHeader>

        <div className="px-5 pb-4">{active?.content}</div>

        <DialogFooter className="-mx-0 -mb-0 flex items-center justify-between gap-2 rounded-b-xl border-t bg-muted/50 px-5 py-3 sm:justify-between">
          <Button
            type="button"
            variant="outline"
            onClick={onPrev}
            disabled={isFirst || isFinishing}
          >
            Quay lại
          </Button>
          {isLast ? (
            <Button
              type="button"
              onClick={onFinish}
              disabled={!canNext || isFinishing}
            >
              {isFinishing ? "Đang lưu..." : "Hoàn tất"}
            </Button>
          ) : (
            <Button
              type="button"
              onClick={onNext}
              disabled={!canNext || isFinishing}
            >
              Tiếp theo
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

interface StepperProps {
  steps: SettingsWizardStep[];
  currentIndex: number;
}

function Stepper({ steps, currentIndex }: StepperProps) {
  return (
    <ol className="flex items-center gap-2" aria-label="Tiến trình">
      {steps.map((step, idx) => {
        const completed = idx < currentIndex;
        const active = idx === currentIndex;
        return (
          <React.Fragment key={step.id}>
            <li
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-medium tabular-nums transition-colors",
                completed && "bg-accent text-accent-foreground",
                active && !completed && "bg-foreground text-background",
                !completed &&
                  !active &&
                  "bg-muted text-muted-foreground ring-1 ring-border",
              )}
            >
              {completed ? (
                <Check className="size-3.5" aria-hidden />
              ) : (
                <span>{idx + 1}</span>
              )}
              <span className="sr-only">{step.title}</span>
            </li>
            {idx < steps.length - 1 ? (
              <li
                aria-hidden
                className={cn(
                  "h-px flex-1 bg-border",
                  idx < currentIndex && "bg-accent",
                )}
              />
            ) : null}
          </React.Fragment>
        );
      })}
    </ol>
  );
}
