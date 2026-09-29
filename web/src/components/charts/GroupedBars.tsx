"use client";

import { scaleLinear } from "d3-scale";
import { type ReactNode, useState } from "react";

import { formatValue } from "@/lib/format";

import { Legend, type LegendItem } from "./Legend";
import { diamondPath, hbarPath } from "./shapes";
import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { fitTicks, textWidth, useWidth } from "./useWidth";

export interface BarSeries {
  key: string;
  label: string;
  /** The legend swatch; a group can paint its bars in its own color instead. */
  color: string;
  pattern?: string;
  opacity?: number;
}
export interface BarGroup {
  key: string;
  label: string;
  values: Record<string, number | null>;
  /** Paint this group's bars in one color, such as its channel's, whatever the series. */
  color?: string;
  marker?: number | null;
  /** A small label beside the group's name, such as the bound a plan sits at. */
  chip?: ReactNode;
}

/**
 * Horizontal bars grouped by category, one bar per series, rounded at the data end, with an
 * optional hollow diamond per group for the truth. Group names sit above their bars so long
 * names never crowd the plot on a phone.
 */
export function GroupedBars({
  groups,
  series,
  fmt,
  axisLabel,
  markerLabel = "truth (simulated)",
  barH = 11,
  showValues = false,
  legend: legendOverride,
  colorBy,
  testId,
}: {
  groups: BarGroup[];
  series: BarSeries[];
  fmt: string;
  axisLabel: string;
  markerLabel?: string;
  barH?: number;
  showValues?: boolean;
  /** A legend of its own, when series share a look and a list of swatches would not help. */
  legend?: LegendItem[];
  /** A color for one bar, by group and series, such as a channel's own color for its plan bar only. */
  colorBy?: (group: string, series: string) => string | undefined;
  testId?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const values = groups
    .flatMap((g) => [...series.map((s) => g.values[s.key] ?? null), g.marker ?? null])
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const valueRoom = showValues ? Math.max(...values.map((v) => textWidth(formatValue(v, fmt), 11))) + 10 : 12;
  const x = scaleLinear()
    .domain([lo, hi === lo ? lo + 1 : hi])
    .nice(5)
    .range([2, Math.max(width - valueRoom, 120)]);
  const ticks = fitTicks(x, width - valueRoom, (t) => formatValue(t, fmt), width < 480 ? 4 : 6);
  const gap = 2;
  const groupH = series.length * (barH + gap) - gap + 6;

  const legend: LegendItem[] =
    legendOverride ?? series.map((s) => ({ label: s.label, color: s.color, kind: "bar", pattern: s.pattern, opacity: s.opacity }));
  if (!legendOverride && groups.some((g) => g.marker !== null && g.marker !== undefined))
    legend.push({ label: markerLabel, color: "var(--ink)", kind: "diamond" });

  return (
    <div ref={ref} className="relative w-full overflow-hidden" onMouseLeave={() => setTip(null)} data-testid={testId}>
      <div className="space-y-2.5">
        {groups.map((g) => (
          <div key={g.key} data-group={g.key}>
            <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[12.5px] text-ink mb-1">
              <span>{g.label}</span>
              {g.chip}
            </div>
            <svg width={width} height={groupH} role="img" aria-label={g.label} className="block">
              {ticks.map((t) => (
                <line
                  key={t}
                  x1={x(t)}
                  x2={x(t)}
                  y1={0}
                  y2={groupH}
                  stroke="var(--hairline)"
                  strokeDasharray={t === 0 ? undefined : "2 3"}
                />
              ))}
              {series.map((s, i) => {
                const v = g.values[s.key];
                if (v === null || v === undefined) return null;
                const y = 3 + i * (barH + gap);
                const d = hbarPath(x(0), x(v), y, barH);
                const fill = colorBy?.(g.key, s.key) ?? g.color ?? s.color;
                const show = (e: Parameters<typeof pointIn>[1]) => {
                  const at = pointIn(ref.current, e);
                  setTip({
                    x: at.x,
                    y: at.y,
                    lines: [
                      g.label,
                      `${s.label}: ${formatValue(v, fmt)}`,
                      g.marker !== null && g.marker !== undefined ? `${markerLabel}: ${formatValue(g.marker, fmt)}` : "",
                    ],
                  });
                };
                return (
                  <g
                    key={s.key}
                    tabIndex={0}
                    onMouseMove={show}
                    onFocus={show}
                    onBlur={() => setTip(null)}
                    className="outline-none"
                    data-testid="bar"
                    data-series={s.key}
                    data-value={v}
                  >
                    <path d={d} fill={fill} opacity={s.opacity} />
                    {s.pattern ? <path d={d} fill={s.pattern} /> : null}
                    {showValues ? (
                      <text
                        x={x(v) + (v >= 0 ? 5 : -5)}
                        y={y + barH / 2}
                        dy="0.35em"
                        textAnchor={v >= 0 ? "start" : "end"}
                        className="fill-[var(--ink)] text-[11px] num"
                      >
                        {formatValue(v, fmt)}
                      </text>
                    ) : null}
                  </g>
                );
              })}
              {g.marker !== null && g.marker !== undefined ? (
                <path
                  d={diamondPath(x(g.marker), groupH / 2, 6)}
                  fill="var(--chart-bg)"
                  fillOpacity={0.4}
                  stroke="var(--ink)"
                  strokeWidth={1.5}
                  data-truth-marker
                  pointerEvents="none"
                />
              ) : null}
            </svg>
          </div>
        ))}
      </div>
      <svg width={width} height={34} aria-hidden="true" className="block mt-1">
        {ticks.map((t) => (
          <text
            key={t}
            x={x(t)}
            y={12}
            textAnchor={x(t) < 24 ? "start" : x(t) > width - 24 ? "end" : "middle"}
            className="fill-[var(--ink2)] text-[11px] num"
          >
            {formatValue(t, fmt)}
          </text>
        ))}
        <text x={width / 2} y={30} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
          {axisLabel}
        </text>
      </svg>
      <Legend items={legend} />
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
