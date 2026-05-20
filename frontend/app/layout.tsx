import type { Metadata } from "next";
import type { ReactNode } from "react";
import { getLocale, getMessages } from "next-intl/server";
import { Providers } from "@/components/providers";
import { ThemeBootstrap } from "@/components/shell/ThemeBootstrap";
import { fontSans, fontGeist, fontMono, fontDisplay, fontMonoAccent } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "StoryForge",
  description: "StoryForge — 2-layer LLM story generation pipeline",
};

export default async function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html
      lang={locale}
      suppressHydrationWarning
      className={`${fontSans.variable} ${fontGeist.variable} ${fontMono.variable} ${fontDisplay.variable} ${fontMonoAccent.variable}`}
    >
      <head>
        {/* Inline theme bootstrap (no FOUC). Runs before paint via beforeInteractive. */}
        <ThemeBootstrap />
      </head>
      <body className="min-h-screen bg-background text-foreground antialiased">
        <Providers locale={locale} messages={messages}>
          {children}
        </Providers>
      </body>
    </html>
  );
}
