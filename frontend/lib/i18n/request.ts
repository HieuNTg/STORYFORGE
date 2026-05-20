import { getRequestConfig } from "next-intl/server";

/**
 * Phase 0: static default locale = `vi`. Cookie-driven switching is intentionally
 * deferred — reading `cookies()` here marks every page as dynamic and blocks
 * `output: 'export'`. Phase 2+ will reintroduce locale switching via a client-side
 * rerender path (NextIntlClientProvider already receives `locale` & `messages` as
 * props in components/providers.tsx, so a future provider swap is straightforward).
 */

const DEFAULT_LOCALE = "vi" as const;

export default getRequestConfig(async () => {
  const messages = (await import(`../../messages/${DEFAULT_LOCALE}.json`)).default;
  return { locale: DEFAULT_LOCALE, messages, timeZone: "Asia/Ho_Chi_Minh" };
});
