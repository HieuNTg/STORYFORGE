import { getTranslations } from "next-intl/server";
import { PipelineScreen } from "@/components/pipeline/PipelineScreen";

export default async function ForgePage() {
  const t = await getTranslations("pages.pipeline");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </header>
      <PipelineScreen />
    </div>
  );
}
