"use client";

/**
 * GuideContent — Vietnamese-language onboarding + FAQ + doc links.
 *
 * Static content only; no data fetching. All routes resolve at static-export
 * time. Designer is free to restyle but keep semantic structure (h2, ul, a).
 */

import * as React from "react";
import Link from "next/link";
import { ArrowRight, BookOpen, Settings, KeyRound, GitBranch, Download, LifeBuoy } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FaqAccordion, type FaqItem } from "./FaqAccordion";

interface StepCardProps {
  icon: LucideIcon;
  title: string;
  description: string;
  href: string;
  cta: string;
}

function StepCard({ icon: Icon, title, description, href, cta }: StepCardProps) {
  return (
    <Card size="sm" className="h-full">
      <CardHeader className="flex flex-row items-center gap-2.5">
        <div className="flex size-9 items-center justify-center rounded-md bg-muted text-foreground">
          <Icon className="size-4" strokeWidth={1.75} aria-hidden="true" />
        </div>
        <CardTitle className="text-base">{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 pb-4">
        <p className="text-sm text-muted-foreground">{description}</p>
        <Link
          href={href}
          className="inline-flex items-center gap-1 text-sm font-medium text-[var(--accent-strong)] hover:underline"
        >
          {cta}
          <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      </CardContent>
    </Card>
  );
}

import { useTranslations } from "next-intl";

export function GuideContent() {
  const t = useTranslations("guide");

  const steps: StepCardProps[] = [
    {
      icon: KeyRound,
      title: t("steps.step_1_title"),
      description: t("steps.step_1_desc"),
      href: "/settings",
      cta: t("steps.step_1_cta"),
    },
    {
      icon: BookOpen,
      title: t("steps.step_2_title"),
      description: t("steps.step_2_desc"),
      href: "/",
      cta: t("steps.step_2_cta"),
    },
    {
      icon: GitBranch,
      title: t("steps.step_3_title"),
      description: t("steps.step_3_desc"),
      href: "/library",
      cta: t("steps.step_3_cta"),
    },
    {
      icon: Download,
      title: t("steps.step_4_title"),
      description: t("steps.step_4_desc"),
      href: "/export",
      cta: t("steps.step_4_cta"),
    },
  ];

  const faq: FaqItem[] = [
    {
      id: "start",
      question: t("faq_items.start_q"),
      answer: (
        <p>
          {t.rich("faq_items.start_a", {
            settingsLink: (chunks) => <Link href="/settings" className="font-medium text-[var(--accent-strong)] hover:underline">{chunks}</Link>,
            strong: (chunks) => <strong>{chunks}</strong>,
          })}
        </p>
      ),
    },
    {
      id: "keys",
      question: t("faq_items.keys_q"),
      answer: (
        <p>
          {t.rich("faq_items.keys_a", {
            code: (chunks) => <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{chunks}</code>,
          })}
        </p>
      ),
    },
    {
      id: "first-story",
      question: t("faq_items.first_story_q"),
      answer: (
        <ol className="list-decimal pl-5 space-y-1">
          <li>
            {t.rich("faq_items.first_story_a_1", {
              strong: (chunks) => <strong>{chunks}</strong>,
            })}
          </li>
          <li>{t("faq_items.first_story_a_2")}</li>
          <li>{t("faq_items.first_story_a_3")}</li>
          <li>{t("faq_items.first_story_a_4")}</li>
          <li>
            {t.rich("faq_items.first_story_a_5", {
              strong: (chunks) => <strong>{chunks}</strong>,
              libraryLink: (chunks) => <Link href="/library" className="font-medium text-[var(--accent-strong)] hover:underline">{chunks}</Link>,
            })}
          </li>
        </ol>
      ),
    },
    {
      id: "branching",
      question: t("faq_items.branching_q"),
      answer: (
        <p>
          {t.rich("faq_items.branching_a", {
            libraryLink: (chunks) => <Link href="/library" className="font-medium text-[var(--accent-strong)] hover:underline">{chunks}</Link>,
          })}
        </p>
      ),
    },
    {
      id: "exports",
      question: t("faq_items.exports_q"),
      answer: (
        <p>
          {t.rich("faq_items.exports_a", {
            strong: (chunks) => <strong>{chunks}</strong>,
            libraryLink: (chunks) => <Link href="/library" className="font-medium text-[var(--accent-strong)] hover:underline">{chunks}</Link>,
          })}
        </p>
      ),
    },
    {
      id: "providers",
      question: t("faq_items.providers_q"),
      answer: (
        <p>
          {t.rich("faq_items.providers_a", {
            code: (chunks) => <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{chunks}</code>,
            providersLink: (chunks) => <Link href="/providers" className="font-medium text-[var(--accent-strong)] hover:underline">{chunks}</Link>,
          })}
        </p>
      ),
    },
    {
      id: "cost",
      question: t("faq_items.cost_q"),
      answer: (
        <p>
          {t.rich("faq_items.cost_a", {
            usageLink: (chunks) => <Link href="/usage" className="font-medium text-[var(--accent-strong)] hover:underline">{chunks}</Link>,
          })}
        </p>
      ),
    },
    {
      id: "troubleshooting",
      question: t("faq_items.troubleshooting_q"),
      answer: (
        <ul className="list-disc pl-5 space-y-1">
          <li>
            {t.rich("faq_items.troubleshooting_a_1", {
              providersLink: (chunks) => <Link href="/providers" className="font-medium text-[var(--accent-strong)] hover:underline">{chunks}</Link>,
            })}
          </li>
          <li>
            {t.rich("faq_items.troubleshooting_a_2", {
              strong: (chunks) => <strong>{chunks}</strong>,
            })}
          </li>
          <li>
            {t.rich("faq_items.troubleshooting_a_3", {
              strong: (chunks) => <strong>{chunks}</strong>,
            })}
          </li>
          <li>
            {t.rich("faq_items.troubleshooting_a_4", {
              githubLink: (chunks) => (
                <a
                  href="https://github.com/xnohat/storyforge/issues"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="font-medium text-[var(--accent-strong)] hover:underline"
                >
                  {chunks}
                </a>
              ),
            })}
          </li>
        </ul>
      ),
    },
  ];

  const links = [
    {
      label: "GitHub repository",
      href: "https://github.com/xnohat/storyforge",
      description: t("links.github_desc"),
    },
    {
      label: "Tài liệu API (FastAPI)",
      href: "/docs",
      description: t("links.api_desc"),
    },
    {
      label: "CLAUDE.md (kiến trúc)",
      href: "https://github.com/xnohat/storyforge/blob/master/CLAUDE.md",
      description: t("links.claude_desc"),
    },
  ];

  return (
    // Phase 4 typography discipline: section headings use the H2 scale
    // (text-xl). FAQ answers inherit `prose-guide` via FaqAccordion, so the
    // line-length cap (~70ch) and body rhythm apply automatically inside
    // each accordion panel.
    <div className="flex flex-col gap-10">
      <section aria-labelledby="getting-started" className="flex flex-col gap-4">
        <h2 id="getting-started" className="text-xl font-semibold tracking-tight">
          {t("quick_start")}
        </h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map((s) => (
            <StepCard key={s.title} {...s} />
          ))}
        </div>
      </section>

      <section aria-labelledby="faq" className="flex flex-col gap-4">
        <h2 id="faq" className="text-xl font-semibold tracking-tight">
          {t("faq")}
        </h2>
        <FaqAccordion items={faq} />
      </section>

      <section aria-labelledby="resources" className="flex flex-col gap-4">
        <h2 id="resources" className="text-xl font-semibold tracking-tight">
          {t("resources")}
        </h2>
        <Card>
          <CardContent className="flex flex-col gap-3 pb-4">
            <ul className="flex flex-col gap-2">
              {links.map((l) => (
                <li key={l.href} className="flex items-start gap-3">
                  <LifeBuoy className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <div className="flex flex-col">
                    <a
                      href={l.href}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-sm font-medium text-foreground hover:underline"
                    >
                      {l.label}
                    </a>
                    <span className="text-xs text-muted-foreground">
                      {l.description}
                    </span>
                  </div>
                </li>
              ))}
              <li className="flex items-start gap-3">
                <Settings className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <div className="flex flex-col">
                  <Link
                    href="/settings"
                    className="text-sm font-medium text-foreground hover:underline"
                  >
                    {t("open_settings")}
                  </Link>
                  <span className="text-xs text-muted-foreground">
                    {t("settings_desc")}
                  </span>
                </div>
              </li>
            </ul>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
