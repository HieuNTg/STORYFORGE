"use client";

import { useTranslations } from "next-intl";
import { BookshelfScreen } from "@/components/library/BookshelfScreen";

export default function LibraryPage() {
  const t = useTranslations("pages.library");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </header>
      <BookshelfScreen />
    </div>
  );
}
