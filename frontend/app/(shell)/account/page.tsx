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
import { BookText, Sparkles } from "lucide-react";

import { PageHero } from "@/components/common/PageHero";
import {
  AccountSummary,
  type AccountQuickLink,
} from "@/components/account/AccountSummary";
import type { StatCardProps } from "@/components/account/StatCard";
import { useStories, useSessionUsage } from "@/lib/api/queries";

function formatNumber(n: number): string {
  return new Intl.NumberFormat("vi-VN").format(n);
}

export default function AccountPage() {
  const stories = useStories({ pageSize: 1 });
  const usage = useSessionUsage();

  const totalStories = stories.data?.pages[0]?.total ?? 0;
  const totalTokens = usage.data?.total_tokens ?? 0;

  const stats: StatCardProps[] = [
    {
      icon: BookText,
      label: "Truyện đã tạo",
      value: stories.isLoading ? "—" : formatNumber(totalStories),
      description: "Tổng số truyện trong thư viện.",
    },
    {
      icon: Sparkles,
      label: "Token đã dùng (phiên)",
      value: usage.isLoading || usage.isError ? "—" : formatNumber(totalTokens),
      description: usage.isError
        ? "Không lấy được số liệu."
        : "Tổng prompt + completion của phiên hiện tại.",
    },
  ];

  const quickLinks: AccountQuickLink[] = [
    {
      label: "Chi tiết sử dụng",
      href: "/usage",
      description: "Bóc tách theo truyện và mô hình.",
    },
    {
      label: "Hướng dẫn",
      href: "/guide",
      description: "Mẹo nhanh để tạo truyện chất lượng cao.",
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title="Tài khoản"
        subtitle="Tổng quan sử dụng StoryForge"
      />
      <AccountSummary stats={stats} quickLinks={quickLinks} />
    </div>
  );
}
