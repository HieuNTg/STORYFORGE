import type { ReactNode } from "react";
import { ThemeToggle } from "./ThemeToggle";
import { LocaleSwitcher } from "./LocaleSwitcher";
import { CommandPaletteTrigger } from "./CommandPalette";

interface TopbarProps {
  breadcrumb?: ReactNode;
}

export function Topbar({ breadcrumb }: TopbarProps) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-border/60 bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
        {breadcrumb}
      </div>
      <div className="flex items-center gap-1.5">
        <CommandPaletteTrigger />
        <LocaleSwitcher />
        <ThemeToggle />
      </div>
    </header>
  );
}
