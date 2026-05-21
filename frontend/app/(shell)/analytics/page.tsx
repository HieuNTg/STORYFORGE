"use client";

import { PageHero } from "@/components/common/PageHero";
import { AnalyticsStartScreen } from "@/components/analytics/AnalyticsStartScreen";

export default function AnalyticsStartPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title="Phân tích"
        subtitle="Chọn một truyện trong thư viện để xem số liệu chương, chất lượng và sự kiện."
      />
      <AnalyticsStartScreen />
    </div>
  );
}
