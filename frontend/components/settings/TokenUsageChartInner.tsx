"use client";

import * as React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";

export interface ChartPoint {
  model: string;
  tokens: number;
  cost: number;
}

export interface TokenUsageChartInnerProps {
  points: ChartPoint[];
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export default function TokenUsageChartInner({ points }: TokenUsageChartInnerProps) {
  return (
    <div className="h-64 w-full rounded-xl border border-accent/30 bg-card/40 p-3">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={points} margin={{ top: 8, right: 12, bottom: 8, left: 0 }}>
          <defs>
            <linearGradient id="goldFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.5} />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="model"
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 11 }}
            interval={0}
            angle={-15}
            textAnchor="end"
            height={48}
          />
          <YAxis
            stroke="var(--muted-foreground)"
            tick={{ fontSize: 11 }}
            tickFormatter={formatTokens}
            width={48}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: "var(--foreground)" }}
            formatter={(value, name) => {
              const n = typeof value === "number" ? value : Number(value ?? 0);
              const key = String(name ?? "");
              if (key === "tokens") return [formatTokens(n), "Tokens"];
              if (key === "cost") return [`$${n.toFixed(4)}`, "Chi phí"];
              return [String(value ?? ""), key];
            }}
          />
          <Area
            type="monotone"
            dataKey="tokens"
            stroke="var(--accent)"
            strokeWidth={1.5}
            fill="url(#goldFill)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
