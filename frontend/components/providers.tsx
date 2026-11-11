"use client";

import { useEffect, useMemo, useState, useSyncExternalStore, type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { NextIntlClientProvider, type AbstractIntlMessages } from "next-intl";
import enMessages from "@/messages/en.json";
import viMessages from "@/messages/vi.json";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Toaster } from "@/components/ui/sonner";
import { makeQueryClient } from "@/lib/query-client";

interface ProvidersProps {
  children: ReactNode;
  locale: string;
  messages: AbstractIntlMessages;
}

const CLIENT_MESSAGES: Record<string, AbstractIntlMessages> = {
  en: enMessages,
  vi: viMessages,
};

function readClientLocale(fallback: string) {
  if (typeof document === "undefined") return fallback;
  const cookieLocale = document.cookie.match(/(?:^|; )NEXT_LOCALE=([^;]*)/)?.[1];
  const storedLocale = window.localStorage.getItem("storyforge_locale");
  const next = cookieLocale ? decodeURIComponent(cookieLocale) : storedLocale;
  return next && next in CLIENT_MESSAGES ? next : fallback;
}

export function Providers({ children, locale, messages }: ProvidersProps) {
  const [queryClient] = useState(() => makeQueryClient());
  // The locale switcher persists the choice (cookie + localStorage) before it
  // dispatches "storyforge:locale", so re-reading the persisted value is enough.
  const clientLocale = useSyncExternalStore(
    (onChange) => {
      window.addEventListener("storyforge:locale", onChange);
      return () => window.removeEventListener("storyforge:locale", onChange);
    },
    () => readClientLocale(locale),
    () => locale,
  );

  const clientMessages = useMemo(
    () => CLIENT_MESSAGES[clientLocale] ?? messages,
    [clientLocale, messages],
  );

  useEffect(() => {
    document.documentElement.lang = clientLocale;
  }, [clientLocale]);

  return (
    <NextIntlClientProvider locale={clientLocale} messages={clientMessages} timeZone="Asia/Ho_Chi_Minh">
      <QueryClientProvider client={queryClient}>
        <NuqsAdapter>
          <TooltipProvider delay={150}>
            {children}
            <Toaster position="top-right" richColors />
          </TooltipProvider>
        </NuqsAdapter>
        {process.env.NODE_ENV !== "production" ? (
          <ReactQueryDevtools initialIsOpen={false} />
        ) : null}
      </QueryClientProvider>
    </NextIntlClientProvider>
  );
}
