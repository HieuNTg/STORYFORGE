"use client";

/**
 * /account — OSS account page (no auth).
 *
 * Surfaces two informational stats:
 *   1. Số truyện đã tạo   ← total from useStories first page
 *   2. Token đã dùng (session) ← useSessionUsage
 *
 * Plus quick links to /usage (detailed breakdown) and /guide.
 */

import * as React from "react";
import { useTranslations, useLocale } from "next-intl";
import { BookText, Sparkles } from "lucide-react";

import { PageHero } from "@/components/common/PageHero";
import {
  AccountSummary,
  type AccountQuickLink,
} from "@/components/account/AccountSummary";
import type { StatCardProps } from "@/components/account/StatCard";
import { useStories, useSessionUsage } from "@/lib/api/queries";

export default function AccountPage() {
  const t = useTranslations("account");
  const locale = useLocale();
  const stories = useStories({ pageSize: 1 });
  const usage = useSessionUsage();

  const totalStories = stories.data?.pages[0]?.total ?? 0;
  const totalTokens = usage.data?.total_tokens ?? 0;

  const formatNumber = (n: number) => {
    return new Intl.NumberFormat(locale).format(n);
  };

  const stats: StatCardProps[] = [
    {
      icon: BookText,
      label: t("stories_created"),
      value: stories.isLoading ? "—" : formatNumber(totalStories),
      description: t("stories_created_desc"),
    },
    {
      icon: Sparkles,
      label: t("tokens_used_session"),
      value: usage.isLoading || usage.isError ? "—" : formatNumber(totalTokens),
      description: usage.isError
        ? t("tokens_used_error")
        : t("tokens_used_session_desc"),
    },
  ];

  const quickLinks: AccountQuickLink[] = [
    {
      label: t("usage_detail"),
      href: "/usage",
      description: t("usage_detail_desc"),
    },
    {
      label: t("guide"),
      href: "/guide",
      description: t("guide_desc"),
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title={t("title")}
        subtitle={t("subtitle")}
      />
      <AccountSummary stats={stats} quickLinks={quickLinks} />
    </div>
  );
}
