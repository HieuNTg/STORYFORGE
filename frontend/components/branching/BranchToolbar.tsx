"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { ChevronLeft, Undo2, Redo2, Bookmark } from "lucide-react";

export interface BranchToolbarProps {
  onBack: () => void;
  onUndo: () => void;
  onRedo: () => void;
  canBack: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onOpenBookmarks: () => void;
  isPending?: boolean;
  className?: string;
}

interface ToolbarButtonProps {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  onClick: () => void;
  disabled?: boolean;
}

function ToolbarButton({
  label,
  icon: Icon,
  onClick,
  disabled,
}: ToolbarButtonProps) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClick}
            disabled={disabled}
            aria-label={label}
          >
            <Icon />
          </Button>
        }
      />
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function BranchToolbar({
  onBack,
  onUndo,
  onRedo,
  canBack,
  canUndo,
  canRedo,
  onOpenBookmarks,
  isPending = false,
  className,
}: BranchToolbarProps) {
  const t = useTranslations("branching");
  const disableAll = isPending;
  return (
    <TooltipProvider>
      <div
        className={cn(
          "flex items-center gap-0.5 rounded-lg border bg-card p-1",
          className
        )}
        role="toolbar"
        aria-label={t("toolbar_title")}
      >
        <ToolbarButton
          label={t("toolbar_back")}
          icon={ChevronLeft}
          onClick={onBack}
          disabled={disableAll || !canBack}
        />
        <ToolbarButton
          label={t("toolbar_undo")}
          icon={Undo2}
          onClick={onUndo}
          disabled={disableAll || !canUndo}
        />
        <ToolbarButton
          label={t("toolbar_redo")}
          icon={Redo2}
          onClick={onRedo}
          disabled={disableAll || !canRedo}
        />
        <span aria-hidden className="mx-0.5 h-5 w-px bg-border" />
        <ToolbarButton
          label={t("toolbar_bookmark")}
          icon={Bookmark}
          onClick={onOpenBookmarks}
          disabled={disableAll}
        />
      </div>
    </TooltipProvider>
  );
}
