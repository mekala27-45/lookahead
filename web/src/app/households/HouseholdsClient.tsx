"use client";

import { useEffect, useMemo } from "react";

import { ChartFrame } from "@/components/charts/ChartFrame";
import { LineChart } from "@/components/charts/LineChart";
import { fmt, whenUtc } from "@/lib/format";
import { markReady } from "@/lib/ready";
import { useMart } from "@/lib/useMart";

interface ProfileRow extends Record<string, unknown> {
  cluster: number;
  daytype: string;
  slot: number;
  ratio: number;
}
interface ClusterRow extends Record<string, unknown> {
  cluster: number;
  shape: string;
  households: number;
  evening_peak_share: number;
}
interface TotalRow extends Record<string, unknown> {
  origin: string;
  horizon: number;
  base_q50: number;
  base_q05: number;
  base_q95: number;
  mint_q50: number;
  actual: number;
}

const when = (value: unknown) => whenUtc(value, "");

export function HouseholdsClient({ profilesCallout, profilesProvenance, totalCallout, totalProvenance }: { profilesCallout: string; profilesProvenance: string; totalCallout: string; totalProvenance: string }) {
  const profiles = useMart<ProfileRow>(`select cluster, daytype, slot, ratio from mart_meter_profiles order by cluster, daytype, slot`);
  const clusters = useMart<ClusterRow>(`select cluster, shape, households, evening_peak_share from mart_meter_clusters order by cluster`);
  const total = useMart<TotalRow>(
    `select origin, horizon, base_q50, base_q05, base_q95, mint_q50, actual from mart_meter_forecast_total where origin = (select max(origin) from mart_meter_forecast_total) order by horizon`,
  );
  useEffect(() => {
    if (profiles.rows || profiles.error) markReady();
  }, [profiles.rows, profiles.error]);
  const byCluster = useMemo(() => {
    const map = new Map<number, ProfileRow[]>();
    for (const r of profiles.rows ?? []) map.set(Number(r.cluster), [...(map.get(Number(r.cluster)) ?? []), r]);
    return map;
  }, [profiles.rows]);
  const yMax = Math.max(1.5, ...(profiles.rows ?? []).map((r) => Number(r.ratio)));
  const info = new Map((clusters.rows ?? []).map((c) => [Number(c.cluster), c]));

  return (
    <>
      <ChartFrame
        title="Load shape clusters: mean weekday and weekend profile as a ratio to the household's mean, one panel per cluster on a shared axis"
        callout={profilesCallout}
        provenance={profilesProvenance}
        table={
          profiles.rows
            ? {
                columns: ["Cluster", "Day type", "Half hour", "Ratio to the household mean"],
                formats: ["int", "text", "int", "float2"],
                rows: profiles.rows.map((r) => [r.cluster, r.daytype, r.slot, r.ratio]),
              }
            : null
        }
        testId="cluster-profiles"
        wide
      >
        {profiles.rows ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[...byCluster.entries()].map(([c, rows]) => {
              const meta = info.get(c);
              return (
                <div key={c} data-cluster={c}>
                  <p className="text-xs text-ink2 mb-1">
                    Cluster {c}: {meta?.shape ?? ""}
                    {meta ? `, ${fmt(meta.households, "int")} households, ${fmt(meta.evening_peak_share, "pct1")} of the evening peak` : ""}
                  </p>
                  <LineChart
                    series={[
                      { key: "weekday", name: "Weekday", points: rows.filter((r) => r.daytype === "weekday").map((r) => ({ x: r.slot / 2, y: r.ratio })), color: `var(--cat-${(c % 8) + 1})`, width: 1.8 },
                      { key: "weekend", name: "Weekend", points: rows.filter((r) => r.daytype === "weekend").map((r) => ({ x: r.slot / 2, y: r.ratio })), color: `var(--cat-${(c % 8) + 1})`, dash: "4 3", width: 1.2 },
                    ]}
                    xFmt="int"
                    yFmt="float1"
                    xLabel="Hour of day"
                    yLabel="Ratio to mean"
                    height={170}
                    compact
                    yDomain={[0, yMax]}
                    xDomain={[0, 23.5]}
                    showLegend={c === 0}
                  />
                </div>
              );
            })}
          </div>
        ) : profiles.error ? (
          <p className="p-4 text-sm text-ink2">{profiles.error}</p>
        ) : (
          <div className="skeleton h-96" />
        )}
      </ChartFrame>

      <div className="mt-5">
        <ChartFrame
          title="The panel total at the last test origin: the direct gbm forecast and the MinT reconciled one against the actual"
          callout={totalCallout}
          provenance={totalProvenance}
          table={
            total.rows
              ? {
                  columns: ["Hours ahead", "Base median", "Base 5%", "Base 95%", "MinT median", "Actual"],
                  formats: ["int", "kwh3", "kwh3", "kwh3", "kwh3", "kwh3"],
                  rows: total.rows.map((r) => [r.horizon, r.base_q50, r.base_q05, r.base_q95, r.mint_q50, r.actual]),
                }
              : null
          }
          testId="meter-total"
        >
          {total.rows && total.rows.length ? (
            <LineChart
              series={[
                { key: "band", name: "Base 90% band", points: [], band: total.rows.map((r) => ({ x: r.horizon, low: r.base_q05, high: r.base_q95 })), color: "var(--seq-5)", label: false },
                { key: "base", name: "Base median", points: total.rows.map((r) => ({ x: r.horizon, y: r.base_q50 })), color: "var(--control)", dash: "4 3" },
                { key: "mint", name: "MinT reconciled median", points: total.rows.map((r) => ({ x: r.horizon, y: r.mint_q50 })), color: "var(--lead)", width: 2 },
                { key: "actual", name: "Actual", points: total.rows.map((r) => ({ x: r.horizon, y: r.actual })), color: "var(--ink)", width: 2 },
              ]}
              xFmt="int"
              yFmt="float0"
              xLabel={`Hours after the origin (${when(String(total.rows[0]?.origin ?? ""))})`}
              yLabel="kWh per hour, panel total"
              height={280}
              zero={false}
            />
          ) : (
            <div className="skeleton h-[280px]" />
          )}
        </ChartFrame>
      </div>
    </>
  );
}
