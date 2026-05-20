"use client";

import * as React from "react";
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

const THEME_LABEL: Record<ReaderTheme, string> = {
  midnight: "Midnight",
  sepia: "Sepia",
  dark: "Tối",
  light: "Sáng",
};

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
  const ThemeIcon = THEME_ICON[theme];

  return (
    <div className={cn("flex items-center gap-1.5", className)}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={onCycleTheme}
        aria-label={`Chủ đề: ${THEME_LABEL[theme]}`}
        title={`Chủ đề: ${THEME_LABEL[theme]}`}
      >
        <ThemeIcon />
        <span className="hidden sm:inline">{THEME_LABEL[theme]}</span>
      </Button>

      <Popover>
        <PopoverTrigger
          render={
            <Button
              type="button"
              variant="outline"
              size="sm"
              aria-label="Tuỳ chỉnh hiển thị"
              title="Tuỳ chỉnh hiển thị"
            >
              <Settings2 />
              <span className="hidden sm:inline">Hiển thị</span>
            </Button>
          }
        />
        <PopoverContent align="end" className="w-80">
          <div className="flex flex-col gap-4">
            {/* Font size */}
            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-medium text-foreground">
                  Cỡ chữ
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
                aria-label="Cỡ chữ"
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
                  Giãn dòng
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
                aria-label="Giãn dòng"
                onValueChange={(v) => {
                  const n = toSingle(v);
                  if (typeof n === "number") onLineHeight(Math.round(n * 100) / 100);
                }}
              />
            </div>

            {/* Font family */}
            <div className="flex flex-col gap-2">
              <label className="text-xs font-medium text-foreground">
                Phông chữ
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
                Độ rộng cột
              </label>
              <Tabs
                value={columnWidth}
                onValueChange={(v) => onColumnWidth(v as ReaderColumnWidth)}
              >
                <TabsList className="w-full">
                  <TabsTrigger value="narrow">Hẹp</TabsTrigger>
                  <TabsTrigger value="medium">Vừa</TabsTrigger>
                  <TabsTrigger value="wide">Rộng</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
