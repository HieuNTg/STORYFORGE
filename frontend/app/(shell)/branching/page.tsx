import { useTranslations } from "next-intl";
import { BranchStartScreen } from "@/components/branching/BranchStartScreen";

export default function BranchingStartPage() {
  const t = useTranslations("branching");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </header>
      <BranchStartScreen />
    </div>
  );
}
