"use client";

/**
 * ApiCallsTable — model usage breakdown table.
 */

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export interface ApiCallsRow {
  model: string;
  tokens: number;
  cost: number;
}

export interface ApiCallsTableProps {
  rows: ApiCallsRow[];
  title?: string;
  className?: string;
}

import { useTranslations, useLocale } from "next-intl";

export function ApiCallsTable({ rows, title, className }: ApiCallsTableProps) {
  const t = useTranslations("usage");
  const locale = useLocale();
  const N = React.useMemo(() => new Intl.NumberFormat(locale), [locale]);

  return (
    <Card className={cn(className)}>
      <CardHeader>
        <CardTitle>{title || t("table_by_model")}</CardTitle>
      </CardHeader>
      <CardContent className="pb-4">
        {rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">{t("model")}</th>
                  <th className="py-2 pr-4 text-right font-medium">{t("tokens")}</th>
                  <th className="py-2 text-right font-medium">{t("cost_usd")}</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.model} className="border-t border-border/60">
                    <td className="py-2 pr-4 font-mono text-xs">{r.model}</td>
                    <td className="py-2 pr-4 text-right tabular-nums">
                      {N.format(r.tokens)}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      ${r.cost.toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
