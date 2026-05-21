import { getTranslations } from "next-intl/server";
import { WandSparkles } from "lucide-react";

export default async function ForgePage() {
  const t = await getTranslations("forge");
  const tNav = await getTranslations("nav_desc");
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-medium text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{tNav("forge")}</p>
      </header>

      <div className="flex flex-col items-center justify-center gap-4 rounded-lg border border-dashed border-border/60 bg-card/40 px-6 py-16 text-center">
        <span className="flex size-12 items-center justify-center rounded-full border border-[var(--accent)]/30 bg-[color-mix(in_oklab,var(--accent)_10%,transparent)]">
          <WandSparkles className="size-5 text-[var(--accent)]" aria-hidden="true" />
        </span>
        <p className="max-w-md text-sm text-muted-foreground">
          {t("placeholder")}
        </p>
        <p className="text-xs uppercase tracking-[0.18em] text-muted-foreground/70">
          Coming soon
        </p>
      </div>
    </div>
  );
}
