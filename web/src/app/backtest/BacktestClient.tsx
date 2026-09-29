"use client";

import { useEffect, useMemo, useState } from "react";

import { ChartFrame, DataTable, type TableData } from "@/components/charts/ChartFrame";
import { Forest, type ForestRow } from "@/components/charts/Forest";
import { GroupedBars } from "@/components/charts/GroupedBars";
import { LineChart } from "@/components/charts/LineChart";
import { Segmented } from "@/components/Controls";
import { markReady } from "@/lib/ready";
import { useMart } from "@/lib/useMart";

interface SkillRow extends Record<string, unknown> {
  backend: string;
  band: string;
  authority: string;
  hours: number;
  model_mape: number;
  operator_mape: number;
  skill: number;
  skill_lower: number;
  skill_upper: number;
  p_value: number;
  verdict: string;
}
interface ReliabilityRow extends Record<string, unknown> {
  backend: string;
  bucket: string;
  level: number;
  share_below: number;
  rows: number;
}
interface RecoveryRow extends Record<string, unknown> {
  condition: string;
  figure: string;
  mean: number;
  lower: number;
  upper: number;
  seeds: number;
}

export interface BacktestTables {
  byAuthority: Record<string, TableData>;
  byHorizon: Record<string, TableData>;
  peaks: Record<string, TableData>;
}

const BANDS: { value: string; label: string }[] = [
  { value: "h1_24", label: "Horizons 1 to 24" },
  { value: "h25_48", label: "Horizons 25 to 48" },
  { value: "target_day", label: "The target day" },
];

const RECOVERY_FIGURES: [string, string, string][] = [
  ["harness.skill_bias", "spct1", "Harness skill bias against the known skill"],
  ["harness.interval_covers_known", "pct0", "Intervals covering the known skill"],
  ["own.coverage_90", "pct1", "own 90 percent coverage (nominal 90)"],
  ["own.thresholds_within_2c", "pct0", "Thresholds recovered within 2 C"],
  ["reconciliation.mint_gain_top", "spct2", "MinT gain at the top against the truth"],
  ["detector.recall_load_shed", "pct0", "Detector recall on planted load sheds"],
  ["detector.recall_defects", "pct0", "Detector recall on planted defects"],
  ["detector.precision_demand_events", "pct0", "Detector precision on demand events"],
];

export function BacktestClient({
  backends,
  served,
  tables,
  skillCallout,
  skillProvenance,
  reliabilityCallout,
  reliabilityProvenance,
  recoveryCallout,
  recoveryProvenance,
  tablesProvenance,
}: {
  backends: string[];
  served: string;
  tables: BacktestTables;
  skillCallout: string;
  skillProvenance: string;
  reliabilityCallout: string;
  reliabilityProvenance: string;
  recoveryCallout: string;
  recoveryProvenance: string;
  tablesProvenance: string;
}) {
  const [backend, setBackend] = useState(served);
  const [band, setBand] = useState("h1_24");
  const skill = useMart<SkillRow>(`select * from mart_skill_rows where backend = '${backend}' and band = '${band}' order by skill desc`);
  const reliability = useMart<ReliabilityRow>(`select * from mart_reliability where bucket = 'all' order by backend, level`);
  const recovery = useMart<RecoveryRow>(`select condition, figure, mean, lower, upper, seeds from mart_recovery order by condition, figure`);
  useEffect(() => {
    if (skill.rows || skill.error) markReady();
  }, [skill.rows, skill.error]);

  const forest: ForestRow[] = useMemo(
    () =>
      (skill.rows ?? []).map((r) => ({
        key: r.authority,
        label: r.authority,
        color: r.verdict === "wins" ? "var(--lead)" : r.verdict === "loses" ? "var(--cat-2)" : "var(--control)",
        estimate: r.skill,
        low: r.skill_lower,
        high: r.skill_upper,
        note: `${r.verdict}, p ${Number(r.p_value).toFixed(3)}`,
      })),
    [skill.rows],
  );
  const options = backends.filter((b) => b !== "seasonal_naive").map((b) => ({ value: b, label: b }));
  const t = (group: Record<string, TableData>) => group[backend] ?? group[served] ?? null;

  return (
    <>
      <div className="flex flex-wrap gap-4 mb-4">
        <Segmented label="Backend" options={options} value={backend} onChange={setBackend} testId="backend-toggle" />
        <Segmented label="Band" options={BANDS} value={band} onChange={setBand} testId="band-toggle" />
      </div>

      <ChartFrame
        title={`Skill against the operator per authority, ${backend}, ${BANDS.find((b) => b.value === band)?.label.toLowerCase()}`}
        callout={skillCallout}
        provenance={skillProvenance}
        table={
          skill.rows
            ? {
                columns: ["Authority", "Hours", "Model MAPE", "Operator MAPE", "Skill", "lower", "upper", "p value", "Verdict"],
                formats: ["text", "int", "pct2", "pct2", "spct1", "spct1", "spct1", "float3", "text"],
                rows: skill.rows.map((r) => [r.authority, r.hours, r.model_mape, r.operator_mape, r.skill, r.skill_lower, r.skill_upper, r.p_value, r.verdict]),
              }
            : null
        }
        testId="skill-forest"
        wide
      >
        {skill.rows ? (
          <Forest
            rows={forest}
            fmt="spct1"
            axisLabel="Skill: 1 minus the model's MAPE over the operator's, with the paired block bootstrap interval"
            reference={{ value: 0, label: "the operator" }}
            estimateLabel="Skill"
            intervalLabel="90% interval"
            testId="skill-forest-chart"
          />
        ) : skill.error ? (
          <p className="p-4 text-sm text-ink2">{skill.error}</p>
        ) : (
          <div className="skeleton h-[600px]" />
        )}
      </ChartFrame>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-5">
        <ChartFrame
          title="The reliability diagram: share of actuals at or below each served level"
          callout={reliabilityCallout}
          provenance={reliabilityProvenance}
          table={
            reliability.rows
              ? {
                  columns: ["Backend", "Level", "Share at or below", "Rows"],
                  formats: ["text", "pct0", "pct1", "int"],
                  rows: reliability.rows.map((r) => [r.backend, r.level, r.share_below, r.rows]),
                }
              : null
          }
          testId="reliability"
        >
          {reliability.rows ? (
            <LineChart
              series={[
                { key: "diagonal", name: "Perfect calibration", points: [{ x: 0, y: 0 }, { x: 1, y: 1 }], color: "var(--control)", dash: "3 3", label: false },
                ...[...new Set(reliability.rows.map((r) => r.backend))].map((b, i) => ({
                  key: b,
                  name: b,
                  points: reliability.rows!.filter((r) => r.backend === b).map((r) => ({ x: r.level, y: r.share_below })),
                  color: i === 0 ? "var(--lead)" : "var(--cat-4)",
                  width: 2,
                })),
              ]}
              xFmt="pct0"
              yFmt="pct0"
              xLabel="Served level"
              yLabel="Share of actuals at or below the level"
              height={280}
              xDomain={[0, 1]}
              yDomain={[0, 1]}
            />
          ) : (
            <div className="skeleton h-[280px]" />
          )}
        </ChartFrame>

        <ChartFrame
          title="The recovery study by condition on the simulator"
          callout={recoveryCallout}
          provenance={recoveryProvenance}
          table={
            recovery.rows
              ? {
                  columns: ["Condition", "Figure", "Mean over seeds", "lower", "upper", "Seeds"],
                  formats: ["text", "text", "float3", "float3", "float3", "int"],
                  rows: recovery.rows.filter((r) => RECOVERY_FIGURES.some(([f]) => f === r.figure)).map((r) => [r.condition, r.figure, r.mean, r.lower, r.upper, r.seeds]),
                }
              : null
          }
          testId="recovery"
        >
          {recovery.rows ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {RECOVERY_FIGURES.filter(([f]) => recovery.rows!.some((r) => r.figure === f)).map(([figure, fmt, label]) => (
                <div key={figure}>
                  <p className="text-xs text-ink2 mb-1">{label}</p>
                  <GroupedBars
                    groups={recovery.rows!
                      .filter((r) => r.figure === figure)
                      .map((r) => ({ key: r.condition, label: r.condition.replace(/_/g, " "), values: { mean: r.mean } }))}
                    series={[{ key: "mean", label: label, color: "var(--lead)" }]}
                    fmt={fmt}
                    axisLabel={label}
                    barH={14}
                    showValues
                  />
                </div>
              ))}
            </div>
          ) : recovery.error ? (
            <p className="p-4 text-sm text-ink2">{recovery.error}</p>
          ) : (
            <div className="skeleton h-[280px]" />
          )}
        </ChartFrame>
      </div>

      <section className="mt-8 space-y-6" aria-label="The backtest tables">
        <div className="card p-4" data-testid="by-horizon">
          <h3 className="font-display text-base mb-2">By horizon, {backend}: the seasonal naive and the operator in the same table</h3>
          <DataTable table={t(tables.byHorizon)} dense max={48} label="By horizon" />
          <p className="text-xs text-ink2 mt-2">{tablesProvenance}</p>
        </div>
        <div className="card p-4" data-testid="by-authority">
          <h3 className="font-display text-base mb-2">By authority, {backend}, all horizons</h3>
          <DataTable table={t(tables.byAuthority)} dense max={60} label="By authority" />
        </div>
        <div className="card p-4" data-testid="peaks">
          <h3 className="font-display text-base mb-2">Peaks and ramps by authority, {backend}: error at the daily peak, its timing, and the morning and evening ramps</h3>
          <DataTable table={t(tables.peaks)} dense max={60} label="Peaks and ramps" />
        </div>
      </section>
    </>
  );
}
