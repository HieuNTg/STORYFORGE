"use client";

import * as React from "react";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard, type StatCardProps } from "./StatCard";

export interface AccountQuickLink {
  label: string;
  href: string;
  description?: string;
}

export interface AccountSummaryProps {
  stats: StatCardProps[];
  quickLinks: AccountQuickLink[];
  className?: string;
}

export function AccountSummary({
  stats,
  quickLinks,
  className,
}: AccountSummaryProps) {
  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {stats.length > 0 ? (
        <div
          className={cn(
            "grid gap-3",
            stats.length >= 3
              ? "sm:grid-cols-2 lg:grid-cols-3"
              : "sm:grid-cols-2",
          )}
        >
          {stats.map((stat, idx) => (
            <StatCard key={`${stat.label}-${idx}`} {...stat} />
          ))}
        </div>
      ) : null}

      {quickLinks.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Liên kết nhanh</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1 pb-2">
            {quickLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="group flex items-center justify-between gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
              >
                <div className="flex flex-col gap-0.5 min-w-0">
                  <span className="truncate text-sm font-medium text-foreground">
                    {link.label}
                  </span>
                  {link.description ? (
                    <span className="truncate text-xs text-muted-foreground">
                      {link.description}
                    </span>
                  ) : null}
                </div>
                <ArrowRight
                  className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5"
                  aria-hidden
                />
              </a>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
