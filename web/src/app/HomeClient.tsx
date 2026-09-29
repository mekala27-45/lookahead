"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChartFrame } from "@/components/charts/ChartFrame";
import { SourceChip, useApiSource } from "@/components/Controls";
import { FanChart, type FanRow } from "@/components/FanChart";
import { Status } from "@/components/Status";
import { TileMap } from "@/components/TileMap";
import { type Answer, read, type ScorecardResponse } from "@/lib/api";
import { fmt } from "@/lib/format";
import type { AuthorityInfo, RegionInfo, Tile } from "@/lib/load";
import { markReady } from "@/lib/ready";
import { useMart } from "@/lib/useMart";

interface AlertRow extends Record<string, unknown> {
  authority: string;
  start: string;
  end: string;
  hours: number;
  kind: string;
  direction: string;
  peak_z: number | null;
  flags: string;
}

interface Lower48Row extends FanRow {
  method: string;
  origin: string;
}

const when = (iso: string) => iso.replace("T", " ").slice(0, 16) + " UTC";

export function HomeClient({
  tiles,
  authorities,
  regions,
  fanCallout,
  fanProvenance,
  alertsCallout,
  alertsProvenance,
}: {
  tiles: Tile[];
  authorities: AuthorityInfo[];
  regions: RegionInfo[];
  fanCallout: string;
  fanProvenance: string;
  alertsCallout: string;
  alertsProvenance: string;
}) {
  const lower48 = useMart<Lower48Row>(`select * from mart_lower48_latest where method = 'mint' order by horizon`);
  const alerts = useMart<AlertRow>(
    `select authority, start, "end", hours, kind, direction, peak_z, flags from mart_events_alerts order by start desc limit 8`,
  );
  const source = useApiSource();
  const [card, setCard] = useState<Answer<ScorecardResponse> | null>(null);
  useEffect(() => {
    let live = true;
    read<ScorecardResponse>("/v1/scorecard", "scorecard").then(
      (a) => {
        if (live) setCard(a);
      },
      () => {
        if (live) setCard(null);
      },
    );
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (lower48.rows || lower48.error) markReady();
  }, [lower48.rows, lower48.error]);

  const origin = lower48.rows?.[0]?.origin ? when(String(lower48.rows[0].origin)) : "";
  return (
    <>
      <TileMap tiles={tiles} authorities={authorities} regions={regions} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5 mt-5">
        <div className="lg:col-span-2">
          <ChartFrame
            title={`The lower 48, the last test origin${origin ? ` (${origin})` : ""}: 48 hours ahead, reconciled by MinT`}
            callout={fanCallout}
            provenance={fanProvenance}
            table={
              lower48.rows
                ? {
                    columns: ["Hours ahead", "Target hour (UTC)", "5%", "25%", "Median", "75%", "95%", "Actual"],
                    formats: ["int", "text", "mw", "mw", "mw", "mw", "mw", "mw"],
                    rows: lower48.rows.map((r) => [r.horizon, when(String(r.target_hour)), r.q05, r.q25, r.q50, r.q75, r.q95, r.actual]),
                  }
                : null
            }
            testId="lower48-fan"
          >
            {lower48.rows ? (
              <FanChart rows={lower48.rows} testId="lower48-fan-chart" />
            ) : lower48.error ? (
              <p className="text-sm text-ink2 p-4">The lower 48 fan could not load: {lower48.error}</p>
            ) : (
              <div className="skeleton h-[300px]" aria-hidden="true" />
            )}
          </ChartFrame>
        </div>
        <div className="space-y-5">
          <div className="card p-4" data-testid="scorecard">
            <div className="flex items-baseline justify-between gap-2 mb-2">
              <h3 className="font-display text-base">The live forecast log</h3>
              <SourceChip source={card ? card.source : source} testId="scorecard-source" />
            </div>
            {card ? (
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                <dt className="text-ink2">Forecasts stored</dt>
                <dd className="num text-right">{fmt(card.body.forecasts, "int")}</dd>
                <dt className="text-ink2">Rows scored</dt>
                <dd className="num text-right">{fmt(card.body.scored_rows, "int")}</dd>
                <dt className="text-ink2">Share still unscored</dt>
                <dd className="num text-right" data-testid="unscored-share">
                  {fmt(card.body.unscored_share, "pct1")}
                </dd>
                <dt className="text-ink2">MAPE of the scored rows</dt>
                <dd className="num text-right">{card.body.mape === null ? "none scored" : fmt(card.body.mape, "pct2")}</dd>
                <dt className="text-ink2">90% coverage</dt>
                <dd className="num text-right">{card.body.coverage_90 === null ? "none scored" : fmt(card.body.coverage_90, "pct1")}</dd>
              </dl>
            ) : (
              <div className="skeleton h-24" aria-hidden="true" />
            )}
            <p className="text-xs text-ink2 mt-2">
              {card?.source === "recorded"
                ? "The API is asleep or unreachable, so this is the recorded session's scorecard."
                : "Scored against the committed actuals until the refresh job exists; the unscored share is the share of stored rows whose actual has not arrived."}
            </p>
          </div>
          <div className="card p-4" data-testid="latest-alerts">
            <h3 className="font-display text-base mb-2">Latest alerts in the test year</h3>
            {alerts.rows ? (
              <ul className="space-y-1.5 text-sm">
                {alerts.rows.map((a) => (
                  <li key={`${a.authority}-${a.start}`} className="flex items-start gap-2">
                    <Status kind={a.kind === "data_defect" ? "warning" : "serious"}>
                      {a.kind === "data_defect" ? "data defect" : "demand event"}
                    </Status>
                    <span>
                      <Link href={`/forecast/${a.authority}/`} className="font-semibold">
                        {a.authority}
                      </Link>{" "}
                      <span className="text-ink2">
                        {when(String(a.start))}, {a.hours} h, {a.direction}
                        {a.peak_z !== null && Number.isFinite(Number(a.peak_z)) ? `, peak z ${fmt(a.peak_z, "float1")}` : ""}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : alerts.error ? (
              <p className="text-sm text-ink2">No alerts loaded: {alerts.error}</p>
            ) : (
              <div className="skeleton h-24" aria-hidden="true" />
            )}
            <p className="text-xs text-ink2 mt-2">{alertsCallout}</p>
            <p className="text-xs text-ink2 mt-1">{alertsProvenance}</p>
          </div>
        </div>
      </div>
    </>
  );
}
