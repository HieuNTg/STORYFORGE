"use client";

/**
 * /export — 5-button export grid, story id from `?id=`.
 *
 * PDF / EPUB / ZIP hit existing backend endpoints. HTML + JSON are
 * client-side blobs (no backend HTML endpoint per phase-05 NF2).
 */

import * as React from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { EmptyState } from "@/components/common/EmptyState";
import { PageHero } from "@/components/common/PageHero";
import { ExportButton } from "@/components/export/ExportButton";

function ExportPageInner() {
  const t = useTranslations("pages.export");
  const search = useSearchParams();
  const id = search.get("id");

  if (!id) {
    return (
      <div className="flex flex-col gap-6">
        <PageHero title={t("title")} subtitle="Chưa chọn truyện" />
        <EmptyState
          variant="export-empty"
          title="Chưa chọn truyện để xuất bản"
          description="Chọn một truyện từ Thư viện, rồi quay lại đây để xuất PDF, EPUB, HTML, ZIP hoặc JSON."
          className="min-h-[320px] rounded-2xl border border-dashed border-border/70 bg-card/35"
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHero title={t("title")} subtitle={`Truyện #${id}`} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        <ExportButton format="pdf" sid={id} />
        <ExportButton format="epub" sid={id} />
        <ExportButton format="html" sid={id} />
        <ExportButton format="zip" sid={id} />
        <ExportButton format="json" sid={id} />
      </div>
    </div>
  );
}

export default function ExportPage() {
  return (
    <React.Suspense
      fallback={
        <div className="flex flex-col gap-6">
          <PageHero title="Xuất bản" subtitle="Đang tải..." />
        </div>
      }
    >
      <ExportPageInner />
    </React.Suspense>
  );
}
