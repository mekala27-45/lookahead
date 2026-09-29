"use client";

import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { type KeyboardEvent, useMemo, useState } from "react";

import { formatValue } from "@/lib/format";

import { PATTERN } from "./Defs";
import { Legend, type LegendItem } from "./Legend";
import { diamondPath } from "./shapes";
import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { fitTicks, textWidth, useWidth } from "./useWidth";

export interface LinePoint {
  x: number;
  y: number | null;
}
export interface LineSeries {
  key: string;
  name: string;
  points: LinePoint[];
  color: string;
  dash?: string;
  width?: number;
  opacity?: number;
  band?: { x: number; low: number | null; high: number | null }[];
  /** False for a series that shares another's legend entry or needs none. */
  legend?: boolean;
  /** False to leave a series out of the direct labels. */
  label?: boolean;
}
export interface VRule {
  x: number;
  label: string;
  color?: string;
  dash?: string;
}
export interface HRule {
  y: number;
  label: string;
  color?: string;
  dash?: string;
}
export interface Shade {
  from: number;
  to: number;
  label: string;
}
export interface PointMark {
  x: number;
  y: number;
  label: string;
  color: string;
  shape?: "dot" | "diamond";
}

type Pt = { x: number; y: number };

/**
 * Lines on one value axis. A legend whenever there are two or more series, and direct labels at
 * the line ends when there are four or fewer; each series has its own dash as well as its own
 * hue. Hover or arrow keys walk the x values and read every series at that point.
 */
export function LineChart({
  series,
  xFmt,
  yFmt,
  xLabel,
  yLabel,
  height = 280,
  vRules = [],
  hRules = [],
  shades = [],
  marks = [],
  yDomain,
  xDomain,
  compact = false,
  zero = true,
  extraLegend = [],
  showLegend = true,
  testId,
}: {
  series: LineSeries[];
  xFmt: string;
  yFmt: string;
  xLabel: string;
  yLabel: string;
  height?: number;
  vRules?: VRule[];
  hRules?: HRule[];
  shades?: Shade[];
  marks?: PointMark[];
  yDomain?: [number, number];
  xDomain?: [number, number];
  compact?: boolean;
  /** False to fit the value axis to the data, for levels (weekly sales) rather than amounts. */
  zero?: boolean;
  extraLegend?: LegendItem[];
  showLegend?: boolean;
  testId?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  const legendSeries = series.filter((s) => s.legend !== false);
  const labelled = series.filter((s) => s.label !== false && s.legend !== false);
  const direct = !compact && legendSeries.length <= 4 && width >= 420;

  const xs = useMemo(() => [...new Set(series.flatMap((s) => s.points.map((p) => p.x)))].sort((a, b) => a - b), [series]);
  const ys = series
    .flatMap((s) => [...s.points.map((p) => p.y), ...(s.band ?? []).flatMap((b) => [b.low, b.high])])
    .concat(
      hRules.map((r) => r.y),
      marks.map((m) => m.y),
    )
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const yLo = yDomain ? yDomain[0] : zero ? Math.min(0, ...ys) : Math.min(...ys);
  const yHi = yDomain ? yDomain[1] : zero ? Math.max(0, ...ys) : Math.max(...ys);
  const y0 = scaleLinear()
    .domain([yLo, yHi === yLo ? yLo + 1 : yHi])
    .nice(compact ? 4 : 5);
  const yTicks = y0.ticks(compact ? 4 : 5);
  const tickW = Math.max(...yTicks.map((t) => textWidth(formatValue(t, yFmt), 11)), 20);
  const longest = Math.max(...labelled.map((s) => textWidth(s.name, 11)), 0);
  const lastX = xDomain ? xDomain[1] : (xs[xs.length - 1] ?? 0);
  const margin = {
    top: vRules.length || shades.length ? 22 : 12,
    // Direct labels need their width; otherwise half of the last tick label, so it is never cut off.
    right: direct ? Math.min(140, longest + 14) : Math.max(14, textWidth(formatValue(lastX, xFmt), 11) / 2 + 4),
    bottom: compact ? 34 : 42,
    left: Math.ceil(tickW) + 12,
  };
  const innerW = Math.max(width - margin.left - margin.right, 80);
  const innerH = height - margin.top - margin.bottom;
  const y = y0.range([innerH, 0]);
  const xLo = xDomain ? xDomain[0] : (xs[0] ?? 0);
  const xHi = xDomain ? xDomain[1] : (xs[xs.length - 1] ?? 1);
  const x = scaleLinear()
    .domain([xLo, xHi === xLo ? xLo + 1 : xHi])
    .range([0, innerW]);
  const xTicks = fitTicks(x, innerW, (t) => formatValue(t, xFmt), compact || width < 480 ? 4 : 6);

  const path = line<LinePoint>()
    .defined((d) => d.y !== null && Number.isFinite(d.y))
    .x((d) => x(d.x))
    .y((d) => y(d.y ?? 0));
  const bandPath = area<{ x: number; low: number | null; high: number | null }>()
    .defined((d) => d.low !== null && d.high !== null)
    .x((d) => x(d.x))
    .y0((d) => y(d.low ?? 0))
    .y1((d) => y(d.high ?? 0));

  // Direct labels at each line's last point, pushed apart so two lines ending close together never
  // print on top of each other.
  const GAP = 13;
  const labels = labelled
    .map((s) => {
      const last = [...s.points].reverse().find((p) => p.y !== null && Number.isFinite(p.y));
      return last ? { key: s.key, name: s.name, y: y(last.y ?? 0), color: s.color } : null;
    })
    .filter((l): l is { key: string; name: string; y: number; color: string } => l !== null)
    .sort((a, b) => a.y - b.y);
  for (let pass = 0; pass < 30; pass += 1) {
    let moved = false;
    for (let i = 1; i < labels.length; i += 1) {
      const above = labels[i - 1];
      const here = labels[i];
      if (above && here && here.y - above.y < GAP) {
        const push = (GAP - (here.y - above.y)) / 2;
        above.y -= push;
        here.y += push;
        moved = true;
      }
    }
    for (const l of labels) l.y = Math.min(Math.max(l.y, 4), innerH);
    if (!moved) break;
  }

  const nearest = (s: LineSeries, at: number): Pt | null => {
    let best: Pt | null = null;
    let gap = Infinity;
    for (const p of s.points) {
      if (p.y === null || !Number.isFinite(p.y)) continue;
      const d = Math.abs(p.x - at);
      if (d < gap) {
        gap = d;
        best = { x: p.x, y: p.y };
      }
    }
    return best;
  };

  const showAt = (index: number, px?: number, py?: number) => {
    const at = xs[index];
    if (at === undefined) return;
    setHover(index);
    const lines = [`${xLabel}: ${formatValue(at, xFmt)}`];
    for (const s of series) {
      const p = nearest(s, at);
      if (p && Math.abs(p.x - at) <= (xHi - xLo) / 200 + 1e-9) lines.push(`${s.name}: ${formatValue(p.y, yFmt)}`);
    }
    setTip({ x: px ?? x(at) + margin.left, y: py ?? margin.top + 8, lines });
  };

  const onMove = (e: Parameters<typeof pointIn>[1]) => {
    const at = pointIn(ref.current, e);
    const value = x.invert(at.x - margin.left);
    let index = 0;
    let gap = Infinity;
    xs.forEach((v, i) => {
      const d = Math.abs(v - value);
      if (d < gap) {
        gap = d;
        index = i;
      }
    });
    showAt(index, at.x, at.y);
  };

  const onKey = (e: KeyboardEvent<SVGRectElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const next = Math.min(
        Math.max((hover ?? (e.key === "ArrowRight" ? -1 : xs.length)) + (e.key === "ArrowRight" ? 1 : -1), 0),
        xs.length - 1,
      );
      showAt(next);
    } else if (e.key === "Escape") {
      setHover(null);
      setTip(null);
    }
  };

  const hoverX = hover !== null ? xs[hover] : undefined;
  const legendItems: LegendItem[] = [
    ...legendSeries.map((s) => ({ label: s.name, color: s.color, kind: "line" as const, dash: s.dash, opacity: s.opacity })),
    ...extraLegend,
  ];

  return (
    <div
      ref={ref}
      className="relative w-full overflow-hidden"
      onMouseLeave={() => {
        setTip(null);
        setHover(null);
      }}
      data-testid={testId}
    >
      {compact ? null : <p className="text-[11px] text-ink2 mb-1">{yLabel}</p>}
      <svg width={width} height={height} role="img" aria-label={`${yLabel} by ${xLabel}`}>
        <g transform={`translate(${margin.left},${margin.top})`}>
          {shades.map((s) => (
            <g key={s.label}>
              <rect x={x(s.from)} y={0} width={Math.max(x(s.to) - x(s.from), 1)} height={innerH} fill={PATTERN.window} />
              <text x={x(s.from) + 4} y={-8} className="fill-[var(--ink2)] text-[10.5px]">
                {s.label}
              </text>
            </g>
          ))}
          {yTicks.map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <line x2={innerW} stroke="var(--hairline)" strokeDasharray={t === 0 ? undefined : "2 3"} />
              <text x={-8} dy="0.32em" textAnchor="end" className="fill-[var(--ink2)] text-[11px] num">
                {formatValue(t, yFmt)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={innerH + 17} textAnchor="middle" className="fill-[var(--ink2)] text-[11px] num">
              {formatValue(t, xFmt)}
            </text>
          ))}
          <text x={innerW / 2} y={innerH + (compact ? 30 : 34)} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
            {xLabel}
          </text>
          {series.map((s) => (s.band ? <path key={`band-${s.key}`} d={bandPath(s.band) ?? ""} fill={s.color} opacity={0.14} /> : null))}
          {hRules.map((r) => (
            <g key={r.label}>
              <line
                x1={0}
                x2={innerW}
                y1={y(r.y)}
                y2={y(r.y)}
                stroke={r.color ?? "var(--control)"}
                strokeWidth={1.5}
                strokeDasharray={r.dash ?? "4 3"}
              />
              <text x={innerW - 2} y={y(r.y) - 5} textAnchor="end" className="fill-[var(--ink2)] text-[10.5px]">
                {r.label}
              </text>
            </g>
          ))}
          {series.map((s) => (
            <path
              key={s.key}
              d={path(s.points) ?? ""}
              fill="none"
              stroke={s.color}
              strokeWidth={s.width ?? 2}
              strokeDasharray={s.dash}
              opacity={s.opacity}
              strokeLinejoin="round"
              strokeLinecap="round"
            />
          ))}
          {vRules.map((r, i) => (
            <g key={r.label} data-vrule={r.label}>
              <line
                x1={x(r.x)}
                x2={x(r.x)}
                y1={-4}
                y2={innerH}
                stroke={r.color ?? "var(--ink)"}
                strokeWidth={1.5}
                strokeDasharray={r.dash}
              />
              <text
                x={x(r.x) + (x(r.x) > innerW * 0.7 ? -4 : 4)}
                y={i % 2 === 0 ? -8 : 8}
                textAnchor={x(r.x) > innerW * 0.7 ? "end" : "start"}
                className="fill-[var(--ink2)] text-[10.5px]"
              >
                {r.label}
              </text>
            </g>
          ))}
          {marks.map((m) =>
            m.shape === "diamond" ? (
              <path key={m.label} d={diamondPath(x(m.x), y(m.y), 6)} fill="none" stroke={m.color} strokeWidth={1.5} data-truth-marker />
            ) : (
              <circle
                key={m.label}
                cx={x(m.x)}
                cy={y(m.y)}
                r={5}
                fill={m.color}
                stroke="var(--chart-bg)"
                strokeWidth={1.5}
                data-mark={m.label}
              />
            ),
          )}
          {hoverX !== undefined ? (
            <g pointerEvents="none">
              <line x1={x(hoverX)} x2={x(hoverX)} y1={0} y2={innerH} stroke="var(--control)" strokeWidth={1} />
              {series.map((s) => {
                const p = nearest(s, hoverX);
                return p ? (
                  <circle
                    key={s.key}
                    cx={x(p.x)}
                    cy={y(p.y)}
                    r={4.5}
                    fill={s.color}
                    stroke="var(--chart-bg)"
                    strokeWidth={1.5}
                    opacity={s.opacity}
                  />
                ) : null;
              })}
            </g>
          ) : null}
          {direct
            ? labels.map((l) => (
                <text key={`label-${l.key}`} x={innerW + 6} y={l.y} dy="0.32em" className="text-[11px]" fill={l.color}>
                  {l.name}
                </text>
              ))
            : null}
          <rect
            x={0}
            y={0}
            width={innerW}
            height={innerH}
            fill="transparent"
            tabIndex={0}
            aria-label={`Read ${yLabel} by ${xLabel}; use the arrow keys`}
            onMouseMove={onMove}
            onKeyDown={onKey}
            onBlur={() => {
              setHover(null);
              setTip(null);
            }}
            className="outline-none focus-visible:stroke-[var(--lead)]"
          />
        </g>
      </svg>
      {showLegend ? <Legend items={legendItems} /> : null}
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
