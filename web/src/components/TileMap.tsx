"use client";

import Link from "next/link";

import type { AuthorityInfo, RegionInfo, Tile } from "@/lib/load";
import { fmt } from "@/lib/format";
import { useMart } from "@/lib/useMart";

import { SourceChip } from "./Controls";

export interface TileRow extends Record<string, unknown> {
  authority: string;
  region: string;
  row: number;
  col: number;
  latest_error: number | null;
  latest_origin: string | null;
  skill_h1_24: number | null;
  verdict: string | null;
  backend: string;
}

// Rust is over forecast, cyan is under forecast; the neutral midpoint is within one percent.
const STEPS = [-0.08, -0.04, -0.02, -0.01, 0.01, 0.02, 0.04, 0.08];
export function divergingStep(error: number | null): number {
  if (error === null || !Number.isFinite(error)) return 5;
  // Over forecast (positive error) takes the rust arm, which is slots 1 to 4; under forecast takes cyan, 6 to 9.
  const e = -error;
  let step = 1;
  for (const boundary of STEPS) if (e > boundary) step += 1;
  return Math.min(Math.max(step, 1), 9);
}

/** One tile per authority in a hand positioned grid by region, colored by the latest error's sign and size. */
export function TileMap({ tiles, authorities, regions }: { tiles: Tile[]; authorities: AuthorityInfo[]; regions: RegionInfo[] }) {
  const { rows, error } = useMart<TileRow>(`select * from mart_tiles order by region, authority`);
  const byAuthority = new Map((rows ?? []).map((r) => [r.authority, r]));
  const info = new Map(authorities.map((a) => [a.authority, a]));
  const regionLabel = new Map(regions.map((r) => [r.code, r.label]));
  const maxRow = Math.max(...tiles.map((t) => t.row)) + 1;
  const maxCol = Math.max(...tiles.map((t) => t.col)) + 1;
  const backend = rows?.[0]?.backend ?? "";
  return (
    <div className="card p-4 sm:p-5" data-testid="tile-map" data-ready={rows ? "true" : undefined}>
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
        <h3 className="font-display text-lg">Every balancing authority, colored by the latest day&apos;s error</h3>
        <SourceChip source="precomputed" text={backend ? `${backend} backend, last test origin` : "loading"} />
      </div>
      {error ? <p className="text-sm text-ink2">The tiles could not load: {error}</p> : null}
      <div className="overflow-x-auto pb-2 [contain:paint]" role="list" aria-label="Balancing authorities">
        <div
          className="grid gap-1.5"
          style={{ gridTemplateRows: `repeat(${maxRow}, 44px)`, gridTemplateColumns: `repeat(${maxCol}, 56px)`, minWidth: `${maxCol * 62}px` }}
        >
          {tiles.map((t) => {
            const r = byAuthority.get(t.authority);
            const a = info.get(t.authority);
            const step = divergingStep(r?.latest_error ?? null);
            const dark = step <= 3 || step >= 8;
            const errorText = r?.latest_error === null || r?.latest_error === undefined ? "no scored hours" : `${fmt(r.latest_error, "spct1")} over the last day`;
            const skillText = r?.skill_h1_24 === null || r?.skill_h1_24 === undefined ? "" : `, skill ${fmt(r.skill_h1_24, "spct1")} (${r.verdict})`;
            return (
              <Link
                key={t.authority}
                href={`/forecast/${t.authority}/`}
                role="listitem"
                data-authority={t.authority}
                data-step={rows ? step : undefined}
                title={`${t.authority}, ${regionLabel.get(t.region) ?? t.region}: ${errorText}${skillText}`}
                className={`tile flex flex-col justify-between rounded px-1.5 py-1 no-underline ${rows ? "" : "skeleton"}`}
                style={{
                  gridRow: t.row + 1,
                  gridColumn: t.col + 1,
                  background: rows ? `var(--div-${step})` : undefined,
                  color: rows ? (dark ? "#F2F5F9" : "#101826") : undefined,
                }}
              >
                <span className="font-display text-[13px] font-semibold leading-none">{t.authority}</span>
                <span className="text-[10px] leading-none opacity-90 num">{r ? (r.latest_error === null ? "n/a" : fmt(r.latest_error, "spct1")) : ""}</span>
                <span className="sr-only">{a ? `${a.region} region` : ""}</span>
              </Link>
            );
          })}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-ink2">
        <span>Over forecast</span>
        <span className="inline-flex gap-0.5" aria-hidden="true">
          {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => (
            <span key={i} className="inline-block w-4 h-3 rounded-sm" style={{ background: `var(--div-${i})` }} />
          ))}
        </span>
        <span>Under forecast</span>
        <span className="ml-auto">Each tile is a link to the authority&apos;s page. Rows follow EIA&apos;s regions west to east; the grid scrolls sideways on a phone.</span>
      </div>
    </div>
  );
}
