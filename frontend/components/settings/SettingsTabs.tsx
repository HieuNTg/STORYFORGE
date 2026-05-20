"use client";

import * as React from "react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

export interface SettingsTabItem {
  id: string;
  label: string;
  content: ReactNode;
}

export interface SettingsTabsProps {
  tabs: SettingsTabItem[];
  defaultTab?: string;
  value?: string;
  onValueChange?: (id: string) => void;
  className?: string;
}

/**
 * Settings tab shell. Horizontal scroll on mobile, vertical sidebar on lg+.
 */
export function SettingsTabs({
  tabs,
  defaultTab,
  value,
  onValueChange,
  className,
}: SettingsTabsProps) {
  const first = tabs[0]?.id;
  const initialValue = value ?? defaultTab ?? first;

  return (
    <Tabs
      value={value}
      defaultValue={initialValue}
      onValueChange={onValueChange}
      orientation="horizontal"
      className={cn(
        "flex w-full flex-col gap-4 lg:flex-row lg:items-start lg:gap-6",
        className,
      )}
    >
      <div className="lg:w-56 lg:shrink-0">
        <div className="-mx-4 overflow-x-auto px-4 lg:mx-0 lg:overflow-visible lg:px-0">
          <TabsList
            variant="line"
            className="h-auto w-max flex-row gap-1 bg-transparent p-0 lg:w-full lg:flex-col lg:items-stretch"
          >
            {tabs.map((tab) => (
              <TabsTrigger
                key={tab.id}
                value={tab.id}
                className="h-9 justify-start whitespace-nowrap px-3 lg:w-full"
              >
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </div>
      </div>
      <div className="min-w-0 flex-1">
        {tabs.map((tab) => (
          <TabsContent key={tab.id} value={tab.id} className="mt-0">
            {tab.content}
          </TabsContent>
        ))}
      </div>
    </Tabs>
  );
}
