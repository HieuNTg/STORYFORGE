import { getTranslations } from "next-intl/server";
import { SimulationView } from "@/components/simulation/SimulationView";

export default async function SimulationPage() {
  const t = await getTranslations("simulation");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </header>
      <SimulationView />
    </div>
  );
}
