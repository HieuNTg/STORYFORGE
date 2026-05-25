"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Sidebar } from "@/components/shell/Sidebar";
import { Topbar } from "@/components/shell/Topbar";

export default function ShellLayout({ children }: { children: ReactNode }) {
  const t = useTranslations("shell");
  return (
    <div className="flex h-screen w-full overflow-hidden">
      {/* Skip link — visible on keyboard focus only. Lets keyboard / screen
       * reader users bypass the sidebar nav (WCAG 2.4.1 Bypass Blocks). */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:bg-background focus:px-3 focus:py-2 focus:text-sm focus:font-medium focus:text-foreground focus:shadow-md focus:outline focus:outline-2 focus:outline-ring"
      >
        {t("skip_link")}
      </a>
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-y-auto bg-background bg-gradient-to-br from-background to-card p-6 focus:outline-none"
        >
          {children}
        </main>
      </div>
    </div>
  );
}
