"use client";

/**
 * /export — single static page, story id read from `?id=` search param.
 *
 * Previously `/export/[id]` with `generateStaticParams = [{id:"demo"}]` and
 * `dynamicParams = false` — that only pre-rendered `/export/demo` and broke
 * for real user-generated story ids under `output: 'export'`. The new shape
 * is one statically-exported page that reads the id at runtime in the client.
 *
 * Next requires `useSearchParams()` to live inside a `<Suspense>` boundary
 * during static export — the inner `<ExportPageInner>` is wrapped below.
 */

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import { PageHero } from "@/components/common/PageHero";
import { ExportClient } from "@/components/export/ExportClient";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

function ExportPageInner() {
  const t = useTranslations("pages.export");
  const search = useSearchParams();
  const id = search.get("id");

  if (!id) {
    return (
      <div className="flex flex-col gap-6">
        <PageHero title={t("title")} subtitle="Chưa chọn truyện" />
        <Card>
          <CardContent className="flex flex-col items-start gap-3 py-6">
            <p className="text-sm text-muted-foreground">
              Vui lòng chọn truyện từ Thư viện để xuất bản.
            </p>
            <Link href="/library/" className={buttonVariants()}>
              Mở Thư viện
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHero title={t("title")} subtitle={`Truyện #${id}`} />
      <ExportClient id={id} />
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
