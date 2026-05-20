"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  Sparkles,
  Library,
  WandSparkles,
  Users,
  Drama,
  GitBranch,
  BookOpen,
  Settings,
  Plug,
  User,
  Images,
  Gauge,
  ChartBar,
  Download,
  Workflow,
  PanelLeftClose,
  PanelLeftOpen,
  type LucideIcon,
} from "lucide-react";
import { useUiStore } from "@/stores/ui-store";
import { Button } from "@/components/ui/button";
import { BackendStatusBadge } from "@/components/shell/BackendStatusBadge";
import { cn } from "@/lib/utils";

interface NavItem {
  key: string;
  href: string;
  icon: LucideIcon;
  /** Prefix used for active matching. */
  match: string;
}

/** Cinema-redesign primary nav (locked at 7, per plan F3). */
const PRIMARY: NavItem[] = [
  { key: "library", href: "/library/", icon: Library, match: "/library" },
  { key: "forge", href: "/forge/", icon: WandSparkles, match: "/forge" },
  { key: "characters", href: "/characters/", icon: Users, match: "/characters" },
  { key: "simulation", href: "/simulation/", icon: Drama, match: "/simulation" },
  { key: "branching", href: "/branching/demo/", icon: GitBranch, match: "/branching" },
  { key: "reader", href: "/reader/", icon: BookOpen, match: "/reader" },
  { key: "settings", href: "/settings/", icon: Settings, match: "/settings" },
];

/** Secondary routes still reachable; visually demoted under "More". */
const MORE: NavItem[] = [
  { key: "pipeline", href: "/", icon: Workflow, match: "/" },
  { key: "providers", href: "/providers/", icon: Plug, match: "/providers" },
  { key: "gallery", href: "/gallery/", icon: Images, match: "/gallery" },
  { key: "analytics", href: "/analytics/demo/", icon: ChartBar, match: "/analytics" },
  { key: "export", href: "/export/", icon: Download, match: "/export" },
  { key: "usage", href: "/usage/", icon: Gauge, match: "/usage" },
  { key: "account", href: "/account/", icon: User, match: "/account" },
  { key: "guide", href: "/guide/", icon: BookOpen, match: "/guide" },
];

function isActive(pathname: string, match: string): boolean {
  if (match === "/") return pathname === "/" || pathname === "";
  return pathname === match || pathname.startsWith(match + "/");
}

function NavLink({
  item,
  active,
  collapsed,
  label,
  description,
}: {
  item: NavItem;
  active: boolean;
  collapsed: boolean;
  label: string;
  description?: string;
}) {
  const Icon = item.icon;
  return (
    <Link
      href={item.href}
      aria-current={active ? "page" : undefined}
      title={collapsed ? label : undefined}
      className={cn(
        "group relative flex items-center gap-3 rounded-md py-2.5 pl-4 pr-3 text-sm transition-all duration-200",
        active
          ? "border-l-2 border-[var(--accent)] bg-[color-mix(in_oklab,var(--accent)_8%,transparent)] text-[var(--accent-strong)]"
          : "border-l-2 border-transparent text-muted-foreground hover:bg-[color-mix(in_oklab,var(--accent)_5%,transparent)] hover:pl-5 hover:text-foreground",
      )}
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      {!collapsed && (
        <span className="flex min-w-0 flex-1 flex-col leading-tight">
          <span className="truncate font-medium">{label}</span>
          {description && (
            <span className="truncate text-[11px] text-muted-foreground">
              {description}
            </span>
          )}
        </span>
      )}
      {active && !collapsed && (
        <span
          aria-hidden="true"
          className="gold-pulse ml-auto size-1.5 shrink-0 rounded-full bg-[var(--accent)]"
        />
      )}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname() ?? "/";
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  const t = useTranslations("nav");
  const tDesc = useTranslations("nav_desc");
  const collapsed = !sidebarOpen;

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-border/60 bg-card text-card-foreground transition-[width] duration-200",
        sidebarOpen ? "w-80" : "w-16",
      )}
      aria-label="Primary"
    >
      {/* Brand block */}
      <div className="flex items-center gap-3 border-b border-border/60 px-4 py-5">
        <Link
          href="/library/"
          className="flex items-center gap-3"
          aria-label="StoryForge"
        >
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border border-[var(--accent)]/30 bg-[color-mix(in_oklab,var(--accent)_10%,transparent)]">
            <Sparkles
              className="size-5 text-[var(--accent)]"
              aria-hidden="true"
            />
          </span>
          {!collapsed && (
            <span className="flex flex-col leading-tight">
              <span
                className="text-lg font-semibold tracking-wide text-[var(--accent-strong)]"
                style={{ fontFamily: "var(--font-display)" }}
              >
                STORYFORGE
              </span>
              <span
                className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground"
                style={{ fontFamily: "var(--font-mono)" }}
              >
                AI Story Studio
              </span>
            </span>
          )}
        </Link>
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto"
          aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
          onClick={toggleSidebar}
        >
          {sidebarOpen ? (
            <PanelLeftClose className="size-4" />
          ) : (
            <PanelLeftOpen className="size-4" />
          )}
        </Button>
      </div>

      <nav className="flex-1 overflow-y-auto py-4">
        <ul className="flex flex-col gap-0.5">
          {PRIMARY.map((item) => {
            const active = isActive(pathname, item.match);
            return (
              <li key={item.key}>
                <NavLink
                  item={item}
                  active={active}
                  collapsed={collapsed}
                  label={t(item.key)}
                  description={!collapsed ? safeDesc(tDesc, item.key) : undefined}
                />
              </li>
            );
          })}
        </ul>

        {!collapsed && (
          <div className="mt-6 px-4 pb-2 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            More
          </div>
        )}
        <ul className="flex flex-col gap-0.5">
          {MORE.map((item) => {
            const active = isActive(pathname, item.match);
            return (
              <li key={item.key}>
                <NavLink
                  item={item}
                  active={active}
                  collapsed={collapsed}
                  label={t(item.key)}
                />
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-border/60 px-3 py-3">
        <BackendStatusBadge collapsed={collapsed} />
      </div>
    </aside>
  );
}

function safeDesc(t: ReturnType<typeof useTranslations>, key: string): string | undefined {
  try {
    const v = t(key);
    return v && v !== key ? v : undefined;
  } catch {
    return undefined;
  }
}
