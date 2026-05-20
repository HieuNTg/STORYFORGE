import { getTranslations } from "next-intl/server";
import { CharactersScreen } from "@/components/characters/CharactersScreen";

export default async function CharactersPage() {
  const t = await getTranslations("characters");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </header>
      <CharactersScreen />
    </div>
  );
}
