"use client";

import { useTranslations } from "next-intl";
import { PageHero } from "@/components/common/PageHero";
import { AnalyticsStartScreen } from "@/components/analytics/AnalyticsStartScreen";

export default function AnalyticsStartPage() {
  const t = useTranslations("analytics");

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title={t("title")}
        subtitle={t("subtitle")}
      />
      <AnalyticsStartScreen />
    </div>
  );
}
