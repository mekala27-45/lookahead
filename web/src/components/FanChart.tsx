"use client";

import { LineChart, type LineSeries } from "@/components/charts/LineChart";

export interface FanRow extends Record<string, unknown> {
  horizon: number;
  target_hour: string;
  q05: number;
  q25: number;
  q50: number;
  q75: number;
  q95: number;
  actual: number | null;
  operator: number | null;
  naive: number | null;
}

const num = (v: unknown): number | null => (v === null || v === undefined ? null : Number.isFinite(Number(v)) ? Number(v) : null);

/**
 * The fan chart the desk reads: hours ahead of the origin on the x axis, megawatts on the y
 * axis, the actual in ink, the median in the lead, the 50 and 90 percent bands in the cyan ramp,
 * the operator's forecast as a thin gold dashed line, the seasonal naive dotted, and the origin
 * as a vertical rule.
 */
export function FanChart({ rows, yLabel = "Megawatts", height = 300, testId, originLabel = "origin" }: { rows: FanRow[]; yLabel?: string; height?: number; testId?: string; originLabel?: string }) {
  const sorted = [...rows].sort((a, b) => a.horizon - b.horizon);
  const series: LineSeries[] = [
    {
      key: "band90",
      name: "90% band",
      points: [],
      band: sorted.map((r) => ({ x: r.horizon, low: num(r.q05), high: num(r.q95) })),
      color: "var(--seq-5)",
      legend: true,
      label: false,
    },
    {
      key: "band50",
      name: "50% band",
      points: [],
      band: sorted.map((r) => ({ x: r.horizon, low: num(r.q25), high: num(r.q75) })),
      color: "var(--seq-4)",
      legend: true,
      label: false,
    },
    { key: "median", name: "Forecast median", points: sorted.map((r) => ({ x: r.horizon, y: num(r.q50) })), color: "var(--lead)", width: 2 },
    { key: "actual", name: "Actual", points: sorted.map((r) => ({ x: r.horizon, y: num(r.actual) })), color: "var(--ink)", width: 2.2 },
    { key: "operator", name: "Operator's day ahead forecast", points: sorted.map((r) => ({ x: r.horizon, y: num(r.operator) })), color: "var(--cat-2)", dash: "6 4", width: 1.4 },
    { key: "naive", name: "Seasonal naive", points: sorted.map((r) => ({ x: r.horizon, y: num(r.naive) })), color: "var(--cat-3)", dash: "2 3", width: 1.2, label: false },
  ];
  return (
    <LineChart
      series={series}
      xFmt="int"
      yFmt="mw"
      xLabel="Hours after the origin"
      yLabel={yLabel}
      height={height}
      vRules={[{ x: 0, label: originLabel, color: "var(--control)", dash: "3 3" }]}
      xDomain={[0, 48]}
      zero={false}
      testId={testId}
    />
  );
}
