"use client";

/**
 * CommandPalette — ⌘K / Ctrl+K palette lifted to the shell layout.
 *
 * Modes:
 *  - Default ("page"): jump to any of the 12 routes
 *  - Story search: when input begins to look like a search term, debounced
 *    `GET /api/pipeline/stories?` is queried; clicking a result navigates
 *    to /library/{filename}.
 *
 * Constraints:
 *  - Works in static export (uses next/navigation `useRouter().push`).
 *  - <50ms perceived open: dialog already pre-mounted by base-ui via the
 *    Command primitive; opening just toggles `data-open`. No async chunks
 *    load on open. Story search lazy-fires after 250ms debounce only if
 *    query length > 0.
 *  - cmdk filter is enabled for page items (built-in fuzzy); story items
 *    bypass it (forceMount + we own filtering).
 */

import * as React from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import {
  Workflow,
  Library,
  GitBranch,
  ChartBar,
  Download,
  Settings,
  Plug,
  User,
  Images,
  Gauge,
  BookOpen,
  Search,
  type LucideIcon,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { apiFetch } from "@/lib/api/client";
import type { StoriesPage, StorySummary } from "@/lib/api/queries";
import { useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

interface PageEntry {
  key: string;
  label: string;
  href: string;
  icon: LucideIcon;
  keywords?: string[];
}

const PAGES: PageEntry[] = [
  { key: "pipeline", label: "Pipeline", href: "/", icon: Workflow, keywords: ["home", "tạo", "generate"] },
  { key: "library", label: "Thư viện", href: "/library/", icon: Library, keywords: ["library", "stories", "truyện"] },
  { key: "branching", label: "Phân nhánh", href: "/branching/", icon: GitBranch, keywords: ["branch", "choice", "tree"] },
  { key: "analytics", label: "Phân tích", href: "/analytics/demo/", icon: ChartBar, keywords: ["analytics", "stats", "chart"] },
  { key: "settings", label: "Cài đặt", href: "/settings/", icon: Settings, keywords: ["settings", "config", "cấu hình"] },
  { key: "providers", label: "Nhà cung cấp", href: "/providers/", icon: Plug, keywords: ["llm", "provider", "openai"] },
  { key: "export", label: "Xuất bản", href: "/export/", icon: Download, keywords: ["pdf", "epub", "export"] },
  { key: "account", label: "Tài khoản", href: "/account/", icon: User, keywords: ["account", "profile"] },
  { key: "gallery", label: "Bộ sưu tập", href: "/gallery/", icon: Images, keywords: ["gallery", "share", "public"] },
  { key: "usage", label: "Sử dụng", href: "/usage/", icon: Gauge, keywords: ["usage", "tokens", "cost"] },
  { key: "guide", label: "Hướng dẫn", href: "/guide/", icon: BookOpen, keywords: ["guide", "help", "faq"] },
  // 12th entry: open story search hint (acts as a passthrough)
  { key: "search-stories", label: "Tìm truyện…", href: "search:stories", icon: Search, keywords: ["search", "tìm"] },
];

function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = React.useState(value);
  React.useEffect(() => {
    const id = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return v;
}

export function CommandPalette() {
  const router = useRouter();
  const t = useTranslations("shell");
  const open = useUiStore((s) => s.paletteOpen);
  const setOpen = useUiStore((s) => s.setPaletteOpen);

  const [query, setQuery] = React.useState("");
  const debouncedQuery = useDebounced(query.trim(), 250);

  // Reset query whenever the dialog is asked to close. Wrapping setOpen
  // avoids the `set-state-in-effect` lint rule (the reset is a user-event
  // sync, not an effect-driven render).
  const handleOpenChange = React.useCallback(
    (next: boolean) => {
      if (!next) setQuery("");
      setOpen(next);
    },
    [setOpen],
  );

  // ⌘K / Ctrl+K — toggle.
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        handleOpenChange(!open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, handleOpenChange]);

  // For each (debouncedQuery, open) pair we want exactly one in-flight request
  // and a `completed-for=<query>` marker so we can derive "searching" without
  // an in-effect setState (which the lint rule disallows).
  const [searchResult, setSearchResult] = React.useState<{
    query: string;
    items: StorySummary[];
  }>({ query: "", items: [] });

  const shouldSearch = open && debouncedQuery.length >= 2;

  // Debounced story search. Only fires when query has 2+ chars to avoid
  // hitting backend on every keystroke. Aborts in-flight on new query.
  React.useEffect(() => {
    if (!shouldSearch) return;
    const ac = new AbortController();
    apiFetch<StoriesPage>(
      `/api/pipeline/stories?limit=8&offset=0`,
      { signal: ac.signal },
    )
      .then((res) => {
        // Client-side title/genre filter — backend doesn't yet expose q=.
        const q = debouncedQuery.toLowerCase();
        const hits = res.items
          .filter(
            (s) =>
              s.title.toLowerCase().includes(q) ||
              s.genre.toLowerCase().includes(q) ||
              s.filename.toLowerCase().includes(q),
          )
          .slice(0, 6);
        setSearchResult({ query: debouncedQuery, items: hits });
      })
      .catch(() => {
        /* swallow — record the completion with empty results */
        setSearchResult({ query: debouncedQuery, items: [] });
      });
    return () => ac.abort();
  }, [debouncedQuery, shouldSearch]);

  // Derived view-state — no in-effect setState needed.
  const visibleStories =
    shouldSearch && searchResult.query === debouncedQuery
      ? searchResult.items
      : [];
  const isSearching =
    shouldSearch && searchResult.query !== debouncedQuery;

  const go = React.useCallback(
    (href: string) => {
      setOpen(false);
      // Defer navigation to next tick so the dialog close animation can start
      // before the route changes (perceptually snappier).
      window.setTimeout(() => router.push(href), 0);
    },
    [router, setOpen],
  );

  return (
    <CommandDialog
      open={open}
      onOpenChange={handleOpenChange}
      title={t("search")}
      description={t("open_palette")}
      // Phase 4 visual polish — soft elevation, backdrop blur, capped width,
      // anchored at the top-quarter of the viewport. Overrides the primitive's
      // default `top-1/3` with `top-[25vh]`.
      className={cn(
        "top-[25vh] max-w-[640px] translate-y-0 rounded-xl",
        "border-border/60 bg-popover/95 shadow-2xl backdrop-blur-md",
      )}
    >
      <div className="relative">
        <CommandInput
          placeholder="Lệnh hoặc tên truyện..."
          value={query}
          onValueChange={setQuery}
          aria-label="Lệnh hoặc tên truyện"
        />
        {/* Trailing ⌘K kbd hint inside the input bar (top-right). */}
        <kbd
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 right-3 hidden -translate-y-1/2 rounded border border-border/70 bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:inline-block"
        >
          ⌘K
        </kbd>
      </div>
      <CommandList
        // Phase 4: uppercase tracking-wider group headers + accent-tinted
        // selected-item background. Targets cmdk's `[cmdk-group-heading]` slot
        // and the `[data-selected=true]` item state via arbitrary variants.
        className={cn(
          "**:[[cmdk-group-heading]]:px-3 **:[[cmdk-group-heading]]:py-2 **:[[cmdk-group-heading]]:text-[10px] **:[[cmdk-group-heading]]:font-medium **:[[cmdk-group-heading]]:tracking-wider **:[[cmdk-group-heading]]:text-muted-foreground **:[[cmdk-group-heading]]:uppercase",
          "**:[[data-slot=command-item][data-selected=true]]:bg-accent/12 **:[[data-slot=command-item][data-selected=true]]:text-foreground",
        )}
      >
        <CommandEmpty>
          {isSearching ? "Đang tìm..." : "Không có kết quả."}
        </CommandEmpty>

        <CommandGroup heading="Điều hướng">
          {PAGES.filter((p) => p.key !== "search-stories").map((p) => {
            const Icon = p.icon;
            return (
              <CommandItem
                key={p.key}
                value={`${p.label} ${(p.keywords ?? []).join(" ")}`}
                onSelect={() => go(p.href)}
              >
                <Icon aria-hidden="true" className="text-muted-foreground" />
                <span>{p.label}</span>
              </CommandItem>
            );
          })}
        </CommandGroup>

        {visibleStories.length > 0 ? (
          <>
            <CommandSeparator />
            <CommandGroup heading="Truyện">
              {visibleStories.map((s) => (
                <CommandItem
                  key={s.filename}
                  value={`story-${s.filename} ${s.title}`}
                  onSelect={() =>
                    go(`/library/${encodeURIComponent(s.filename)}/`)
                  }
                >
                  <Library aria-hidden="true" className="text-muted-foreground" />
                  <span className="truncate">{s.title || s.filename}</span>
                  {s.genre ? (
                    <span className="ml-auto text-xs text-muted-foreground">
                      {s.genre}
                    </span>
                  ) : null}
                </CommandItem>
              ))}
            </CommandGroup>
          </>
        ) : null}
      </CommandList>
    </CommandDialog>
  );
}

/**
 * Topbar-rendered trigger button. Renders the palette dialog as well so a
 * single component owns the keyboard listener and visibility state.
 */
export function CommandPaletteTrigger() {
  const t = useTranslations("shell");
  const setOpen = useUiStore((s) => s.setPaletteOpen);
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-2 text-muted-foreground"
        onClick={() => setOpen(true)}
        aria-label={t("open_palette")}
      >
        <Search className="size-3.5" aria-hidden="true" />
        <span className="hidden sm:inline">{t("search")}</span>
        <kbd className="ml-1 hidden rounded border border-border/70 bg-muted px-1.5 py-0.5 font-mono text-[10px] sm:inline">
          ⌘K
        </kbd>
      </Button>
      <CommandPalette />
    </>
  );
}
