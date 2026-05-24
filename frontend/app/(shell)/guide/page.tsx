import { useTranslations } from "next-intl";
import { PageHero } from "@/components/common/PageHero";
import { GuideContent } from "@/components/guide/GuideContent";

export default function GuidePage() {
  const t = useTranslations("guide");

  return (
    <div className="flex flex-col gap-6">
      <PageHero
        title={t("title")}
        subtitle={t("subtitle")}
      />
      <GuideContent />
    </div>
  );
}
