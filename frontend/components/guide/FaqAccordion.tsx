"use client";

/**
 * FaqAccordion — keyboard-accessible accordion built on @base-ui/react/accordion.
 * Single FAQ list, multiple items can be open simultaneously.
 */

import * as React from "react";
import { Accordion } from "@base-ui/react/accordion";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

export interface FaqItem {
  id: string;
  question: string;
  answer: React.ReactNode;
}

export interface FaqAccordionProps {
  items: FaqItem[];
  className?: string;
}

export function FaqAccordion({ items, className }: FaqAccordionProps) {
  return (
    <Accordion.Root
      className={cn(
        "flex flex-col divide-y divide-border/60 rounded-lg border border-border/60 bg-card",
        className,
      )}
    >
      {items.map((it) => (
        <Accordion.Item key={it.id} value={it.id} className="group">
          <Accordion.Header>
            <Accordion.Trigger
              className={cn(
                "flex w-full items-center justify-between gap-4 px-4 py-3 text-left text-sm font-medium",
                "transition-colors hover:bg-muted/50 data-[panel-open]:bg-muted/30",
                "focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring",
              )}
            >
              <span>{it.question}</span>
              <ChevronDown
                aria-hidden="true"
                className="size-4 shrink-0 text-muted-foreground transition-transform duration-[var(--duration-fast)] group-data-[panel-open]:rotate-180"
              />
            </Accordion.Trigger>
          </Accordion.Header>
          <Accordion.Panel className="overflow-hidden px-4 pb-4 text-sm">
            {/* `prose-guide` enforces the 70ch line cap + 1.7 leading + link
             * underline + `<code>` chip styling site-wide. Defined in
             * globals.css. */}
            <div className="prose-guide text-sm">{it.answer}</div>
          </Accordion.Panel>
        </Accordion.Item>
      ))}
    </Accordion.Root>
  );
}
