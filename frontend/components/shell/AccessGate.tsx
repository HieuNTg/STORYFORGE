"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { ApiError } from "@/lib/api/client";
import { getSession, openSession } from "@/lib/api/session";

/** Blocks the app behind a token prompt when the API requires one. */
export function AccessGate({ children }: { children: ReactNode }) {
  const t = useTranslations("access");
  const queryClient = useQueryClient();
  const [token, setToken] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  const { data, isPending } = useQuery({
    queryKey: ["session"],
    queryFn: getSession,
    retry: false,
  });

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setInvalid(false);
    setFailed(false);
    try {
      await openSession(token);
      await queryClient.invalidateQueries();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) setInvalid(true);
      else setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  // Render nothing until the check resolves so protected UI never flashes.
  if (isPending) return null;
  // If the check itself failed, fall through to the app (its own errors surface).
  if (!data || !data.required || data.valid) return <>{children}</>;

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4">
        <h1 className="text-xl font-semibold">{t("title")}</h1>
        <div className="space-y-2">
          <label htmlFor="access-token" className="text-sm font-medium">
            {t("tokenLabel")}
          </label>
          <input
            id="access-token"
            type="password"
            autoComplete="current-password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          />
          {invalid && (
            <p role="alert" className="text-sm text-destructive">
              {t("invalid")}
            </p>
          )}
          {failed && (
            <p role="alert" className="text-sm text-destructive">
              {t("error")}
            </p>
          )}
        </div>
        <button
          type="submit"
          disabled={busy || !token}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {t("submit")}
        </button>
      </form>
    </div>
  );
}
