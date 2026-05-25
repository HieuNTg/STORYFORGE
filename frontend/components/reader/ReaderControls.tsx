"use client";

import * as React from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Settings2, Sun, Leaf, Moon, Sparkles } from "lucide-react";
import type { ReaderTheme, ReaderColumnWidth } from "./ReaderShell";
import type { ReaderFontFamily } from "./ChapterReader";

export interface ReaderControlsProps {
  fontSize: number;
  onFontSize: (n: number) => void;
  lineHeight: number;
  onLineHeight: (n: number) => void;
  fontFamily: ReaderFontFamily;
  onFontFamily: (f: ReaderFontFamily) => void;
  theme: ReaderTheme;
  onCycleTheme: () => void;
  columnWidth: ReaderColumnWidth;
  onColumnWidth: (w: ReaderColumnWidth) => void;
  className?: string;
}

// Removed local THEME_LABEL mapping in favor of next-intl dictionary keys

const THEME_ICON: Record<ReaderTheme, React.ComponentType<{ className?: string }>> = {
  midnight: Sparkles,
  sepia: Leaf,
  dark: Moon,
  light: Sun,
};

/**
 * Single Number<->Slider helper. base-ui Slider returns number | number[];
 * we only use single-thumb sliders here so we coerce to number.
 */
function toSingle(value: number | readonly number[] | undefined): number | undefined {
  if (typeof value === "number") return value;
  if (Array.isArray(value) && value.length > 0) return value[0];
  return undefined;
}

export function ReaderControls({
  fontSize,
  onFontSize,
  lineHeight,
  onLineHeight,
  fontFamily,
  onFontFamily,
  theme,
  onCycleTheme,
  columnWidth,
  onColumnWidth,
  className,
}: ReaderControlsProps) {
  const t = useTranslations("reader");
  const ThemeIcon = THEME_ICON[theme];
  const themeLabel = t(`theme_${theme}` as const);

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onCycleTheme}
        aria-label={t("theme_label", { name: themeLabel })}
        title={t("theme_label", { name: themeLabel })}
      >
        <ThemeIcon />
        <span className="hidden sm:inline">{themeLabel}</span>
      </Button>

      <Popover>
        <PopoverTrigger
          render={
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label={t("display_settings_title")}
              title={t("display_settings_title")}
            >
              <Settings2 />
              <span className="hidden sm:inline">{t("display_settings")}</span>
            </Button>
          }
        />
        <PopoverContent align="end" className="w-80">
          <div className="flex flex-col gap-4">
            {/* Font size */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-foreground">
                  {t("font_size")}
                </label>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {fontSize}px
                </span>
              </div>
              <Slider
                min={12}
                max={22}
                step={1}
                value={[fontSize]}
                aria-label={t("font_size")}
                onValueChange={(v) => {
                  const n = toSingle(v);
                  if (typeof n === "number") onFontSize(n);
                }}
              />
            </div>

            {/* Line height */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-foreground">
                  {t("line_height")}
                </label>
                <span className="text-xs tabular-nums text-muted-foreground">
                  {lineHeight.toFixed(2)}
                </span>
              </div>
              <Slider
                min={1.3}
                max={2.0}
                step={0.05}
                value={[lineHeight]}
                aria-label={t("line_height")}
                onValueChange={(v) => {
                  const n = toSingle(v);
                  if (typeof n === "number") onLineHeight(Math.round(n * 100) / 100);
                }}
              />
            </div>

            {/* Font family */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-foreground">
                {t("font_family")}
              </label>
              <Tabs
                value={fontFamily}
                onValueChange={(v) => onFontFamily(v as ReaderFontFamily)}
              >
                <TabsList className="w-full">
                  <TabsTrigger value="sans">Sans</TabsTrigger>
                  <TabsTrigger value="serif" className="font-serif">
                    Serif
                  </TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            {/* Column width */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-foreground">
                {t("column_width")}
              </label>
              <Tabs
                value={columnWidth}
                onValueChange={(v) => onColumnWidth(v as ReaderColumnWidth)}
              >
                <TabsList className="w-full">
                  <TabsTrigger value="narrow">{t("width_narrow")}</TabsTrigger>
                  <TabsTrigger value="medium">{t("width_medium")}</TabsTrigger>
                  <TabsTrigger value="wide">{t("width_wide")}</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
