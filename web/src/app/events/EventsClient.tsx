"use client";

import { useEffect, useMemo, useState } from "react";

import { ChartFrame } from "@/components/charts/ChartFrame";
import { Heatmap } from "@/components/charts/Heatmap";
import { LineChart } from "@/components/charts/LineChart";
import { Segmented } from "@/components/Controls";
import { Status } from "@/components/Status";
import { fmt, whenUtc } from "@/lib/format";
import type { AuthorityInfo } from "@/lib/load";
import { markReady } from "@/lib/ready";
import { useMart } from "@/lib/useMart";

interface HeatRow extends Record<string, unknown> {
  day: string;
  hour: number;
  z: number;
}
interface AlertRow extends Record<string, unknown> {
  authority: string;
  start: string;
  end: string;
  hours: number;
  kind: string;
  direction: string;
  peak_z: number | null;
  mean_z: number | null;
  flags: string;
}
interface WindowRow extends Record<string, unknown> {
  event: string;
  authority: string;
  utc_hour: string;
  pred: number | null;
  demand_raw: number | null;
  z: number | null;
}

const when = (value: unknown) => whenUtc(value);

export function EventsClient({
  authorities,
  defaultAuthority,
  knownEvents,
  heatmapCallout,
  heatmapProvenance,
  knownCallout,
  knownProvenance,
}: {
  authorities: AuthorityInfo[];
  defaultAuthority: string;
  knownEvents: { event: string; node: string; onset_utc: string; end_utc: string; description: string }[];
  heatmapCallout: string;
  heatmapProvenance: string;
  knownCallout: string;
  knownProvenance: string;
}) {
  const [authority, setAuthority] = useState(defaultAuthority);
  const [known, setKnown] = useState(knownEvents[0] ? `${knownEvents[0].event}|${knownEvents[0].node}` : "");
  const heat = useMart<HeatRow>(`select cast(day as varchar) as day, hour, z from mart_residual_heatmap where authority = '${authority}' order by day, hour`);
  const alerts = useMart<AlertRow>(`select * from mart_events_alerts where authority = '${authority}' order by start`);
  const [knownEvent, knownNode] = known.split("|");
  const window = useMart<WindowRow>(
    knownEvent ? `select event, authority, utc_hour, pred, demand_raw, z from mart_known_event_windows where event = '${knownEvent}' and authority = '${knownNode}' order by utc_hour` : null,
  );
  useEffect(() => {
    if (heat.rows || heat.error) markReady();
  }, [heat.rows, heat.error]);

  const grid = useMemo(() => {
    const rows = heat.rows ?? [];
    const days = [...new Set(rows.map((r) => r.day))].sort();
    const hours = Array.from({ length: 24 }, (_, i) => i);
    const lookup = new Map(rows.map((r) => [`${r.day}|${r.hour}`, Math.max(-6, Math.min(6, Number(r.z)))]));
    return {
      days,
      cells: hours.map((h) => days.map((d) => lookup.get(`${d}|${h}`) ?? null)),
      hours: hours.map((h) => `${String(h).padStart(2, "0")}:00`),
    };
  }, [heat.rows]);
  const options = authorities.map((a) => ({ value: a.authority, label: a.authority }));
  const chosen = knownEvents.find((e) => `${e.event}|${e.node}` === known);

  return (
    <>
      <div className="card p-3 mb-4 flex flex-wrap items-center gap-3">
        <label className="text-xs text-ink2">
          Authority
          <select className="ml-2" value={authority} onChange={(e) => setAuthority(e.target.value)} data-testid="events-authority" aria-label="Authority for the heatmap">
            {options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <ChartFrame
        title={`${authority}: standardized residual of the day's own forecast, every hour of the test year`}
        callout={heatmapCallout}
        provenance={heatmapProvenance}
        table={
          alerts.rows
            ? {
                columns: ["Start (UTC)", "End (UTC)", "Hours", "Class", "Direction", "Peak z", "Mean z", "Quarantine flags"],
                formats: ["text", "text", "int", "text", "text", "float1", "float1", "text"],
                rows: alerts.rows.map((a) => [when(a.start), when(a.end), a.hours, a.kind.replace("_", " "), a.direction, a.peak_z, a.mean_z, a.flags]),
              }
            : null
        }
        testId="residual-heatmap"
        wide
      >
        {heat.rows ? (
          <Heatmap rows={grid.hours} columns={grid.days} cells={grid.cells} fmt="float1" rowLabel="Hour of day (UTC)" columnLabel="Day of the test year" testId="residual-heatmap-chart" />
        ) : heat.error ? (
          <p className="p-4 text-sm text-ink2">{heat.error}</p>
        ) : (
          <div className="skeleton h-[420px]" />
        )}
      </ChartFrame>

      <div className="card p-4 mt-5" data-testid="alerts-list">
        <h3 className="font-display text-base mb-2">Alerts for {authority} in the test year, with their class</h3>
        {alerts.rows ? (
          alerts.rows.length ? (
            <ul className="text-sm space-y-1">
              {alerts.rows.map((a) => (
                <li key={`${a.start}`} className="flex flex-wrap items-baseline gap-2">
                  <Status kind={a.kind === "data_defect" ? "warning" : "serious"}>{a.kind.replace("_", " ")}</Status>
                  <span className="text-ink2">
                    {when(a.start)} to {when(a.end)}, {a.hours} h, {a.direction}
                    {a.peak_z !== null && Number.isFinite(Number(a.peak_z)) ? `, peak z ${fmt(a.peak_z, "float1")}` : ""}
                    {a.flags !== "none" ? `, flags: ${a.flags.replaceAll("_", " ")}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-ink2">No alert for {authority} over the test year.</p>
          )
        ) : (
          <div className="skeleton h-16" />
        )}
      </div>

      <div className="mt-8">
        <Segmented
          label="Known event"
          options={knownEvents.map((e) => ({ value: `${e.event}|${e.node}`, label: `${e.event.replace(/_/g, " ")} at ${e.node}` }))}
          value={known}
          onChange={setKnown}
          testId="known-event-toggle"
        />
        <div className="mt-3">
          <ChartFrame
            title={chosen ? `${chosen.event.replace(/_/g, " ")} at ${chosen.node}: the forecast that had seen nothing after each origin, against what the feed reported` : "Known events"}
            callout={`${chosen?.description ?? ""} ${knownCallout}`}
            provenance={knownProvenance}
            table={
              window.rows
                ? {
                    columns: ["Hour (UTC)", "Forecast median", "Reported demand", "Standardized residual"],
                    formats: ["text", "mw", "mw", "float1"],
                    rows: window.rows.map((r) => [when(r.utc_hour), r.pred, r.demand_raw, r.z]),
                  }
                : null
            }
            testId="known-event-window"
            wide
          >
            {window.rows && chosen ? (
              <LineChart
                series={[
                  { key: "pred", name: "Forecast median", points: window.rows.map((r, i) => ({ x: i, y: r.pred })), color: "var(--lead)", width: 1.6 },
                  { key: "actual", name: "Reported demand", points: window.rows.map((r, i) => ({ x: i, y: r.demand_raw })), color: "var(--ink)", width: 1.8 },
                ]}
                xFmt="int"
                yFmt="mw"
                xLabel={`Hours from ${when(String(window.rows[0]?.utc_hour ?? ""))}`}
                yLabel="Megawatts"
                height={300}
                zero={false}
                shades={[
                  {
                    from: Math.max(0, window.rows.findIndex((r) => String(r.utc_hour) >= chosen.onset_utc.replace("Z", "").replace("T", " ").slice(0, 19).replace(" ", "T"))),
                    to: (() => {
                      const end = window.rows.findIndex((r) => String(r.utc_hour) > chosen.end_utc.replace("Z", ""));
                      return end < 0 ? window.rows.length - 1 : end;
                    })(),
                    label: "the known event",
                  },
                ]}
              />
            ) : (
              <div className="skeleton h-[300px]" />
            )}
          </ChartFrame>
        </div>
      </div>
    </>
  );
}
