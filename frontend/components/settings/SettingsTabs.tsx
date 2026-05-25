"use client";

import * as React from "react";
import type { ReactNode } from "react";
import { KeyRound, Settings2, SlidersHorizontal, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

import { useTranslations } from "next-intl";

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

const TAB_META: Record<
  string,
  {
    descKey: string;
    icon: React.ComponentType<{ className?: string }>;
  }
> = {
  general: {
    descKey: "tab_general_desc",
    icon: Settings2,
  },
  "api-keys": {
    descKey: "tab_api_desc",
    icon: KeyRound,
  },
  "advanced-l1": {
    descKey: "tab_l1_desc",
    icon: SlidersHorizontal,
  },
  "advanced-l2": {
    descKey: "tab_l2_desc",
    icon: Sparkles,
  },
};

/**
 * Settings tab shell. Uses high-contrast pill navigation and a carded panel so
 * tab changes are visually obvious on the warm parchment background.
 */
export function SettingsTabs({
  tabs,
  defaultTab,
  value,
  onValueChange,
  className,
}: SettingsTabsProps) {
  const t = useTranslations("settings_panel");
  const first = tabs[0]?.id;
  const initialValue = value ?? defaultTab ?? first;
  const activeId = value ?? initialValue;
  const activeTab = tabs.find((tab) => tab.id === activeId) ?? tabs[0];
  const activeMeta = activeTab ? TAB_META[activeTab.id] : undefined;
  const ActiveIcon = activeMeta?.icon;

  return (
    <Tabs
      value={value}
      defaultValue={initialValue}
      onValueChange={onValueChange}
      orientation="horizontal"
      className={cn("w-full", className)}
    >
      <section className="grid w-full max-w-none gap-4 rounded-2xl border border-border/70 bg-card/35 p-3 shadow-sm shadow-black/5 lg:grid-cols-[260px_minmax(0,1fr)] lg:p-4">
        <aside className="rounded-xl border border-border/60 bg-background/55 p-2 shadow-inner shadow-black/[0.03]">
          <div className="mb-2 hidden px-2 py-1 lg:block">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              {t("groups_title")}
            </p>
          </div>
          <div className="-mx-1 overflow-x-auto px-1 lg:mx-0 lg:overflow-visible lg:px-0">
            <TabsList
              variant="line"
              className="h-auto w-max flex-row gap-2 bg-transparent p-0 lg:w-full lg:flex-col lg:items-stretch"
            >
              {tabs.map((tab) => {
                const meta = TAB_META[tab.id];
                const Icon = meta?.icon ?? Settings2;
                return (
                  <TabsTrigger
                    key={tab.id}
                    value={tab.id}
                    className={cn(
                      "group h-auto min-w-[140px] justify-start rounded-xl border border-transparent px-3 py-3 text-left transition-all duration-200 lg:w-full",
                      "hover:-translate-y-0.5 hover:border-accent/35 hover:bg-accent/10 hover:text-foreground hover:shadow-sm",
                      "data-active:border-accent/60 data-active:bg-gradient-to-r data-active:from-accent/25 data-active:to-accent/10 data-active:text-foreground data-active:shadow-md data-active:shadow-accent/10",
                      "after:hidden",
                    )}
                  >
                    <span className="flex w-full items-start gap-3">
                      <span className="mt-0.5 rounded-lg border border-border/60 bg-background/70 p-1.5 text-muted-foreground transition-colors group-data-active:text-accent">
                        <Icon className="size-4" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold">
                          {tab.label}
                        </span>
                        {meta?.descKey ? (
                          <span className="mt-0.5 hidden text-wrap text-[11px] leading-snug text-muted-foreground lg:block">
                            {t(meta.descKey)}
                          </span>
                        ) : null}
                      </span>
                    </span>
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </div>
        </aside>

        <div className="min-w-0 w-full overflow-hidden rounded-xl border border-border/70 bg-background/65 shadow-sm">
          {activeTab ? (
            <div className="flex items-center gap-3 border-b border-border/70 bg-gradient-to-r from-accent/12 via-background/80 to-background/40 px-4 py-3">
              {ActiveIcon ? (
                <span className="rounded-lg border border-accent/25 bg-accent/15 p-2 text-accent">
                  <ActiveIcon className="size-4" />
                </span>
              ) : null}
              <div className="min-w-0">
                <h2 className="truncate font-serif text-lg text-foreground">
                  {activeTab.label}
                </h2>
                {activeMeta?.descKey ? (
                  <p className="text-xs text-muted-foreground">
                    {t(activeMeta.descKey)}
                  </p>
                ) : null}
              </div>
            </div>
          ) : null}

          <div className="w-full p-4">
            {tabs.map((tab) => (
              <TabsContent key={tab.id} value={tab.id} className="mt-0">
                <div className="animate-in fade-in-0 slide-in-from-bottom-1 duration-200">
                  {tab.content}
                </div>
              </TabsContent>
            ))}
          </div>
        </div>
      </section>
    </Tabs>
  );
}
