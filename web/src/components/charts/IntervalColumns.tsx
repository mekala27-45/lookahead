"use client";

import { scaleBand, scaleLinear } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { textWidth, useWidth } from "./useWidth";

export interface ColumnPoint {
  key: string;
  short: string;
  label: string;
  color: string;
  value: number | null;
  low: number | null;
  high: number | null;
}

/**
 * One panel of a small multiple: categories along x, a point and its interval for each, on a y
 * domain the caller shares across panels, with one reference line (zero, a floor, a nominal level).
 */
export function IntervalColumns({
  title,
  subtitle,
  points,
  fmt,
  yDomain,
  reference,
  height = 190,
}: {
  title: string;
  subtitle?: string;
  points: ColumnPoint[];
  fmt: string;
  yDomain: [number, number];
  reference?: { y: number; label: string };
  height?: number;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(320);
  const [tip, setTip] = useState<Tip | null>(null);
  const y0 = scaleLinear().domain(yDomain);
  const ticks = y0.ticks(4);
  const margin = {
    top: 10,
    right: 6,
    bottom: 22,
    left: Math.ceil(Math.max(...ticks.map((t) => textWidth(formatValue(t, fmt), 10.5)))) + 12,
  };
  const innerW = Math.max(width - margin.left - margin.right, 60);
  const innerH = height - margin.top - margin.bottom;
  const y = y0.range([innerH, 0]);
  const x = scaleBand<string>()
    .domain(points.map((p) => p.key))
    .range([0, innerW])
    .padding(0.3);
  const clamp = (v: number) => Math.min(Math.max(v, yDomain[0]), yDomain[1]);
  return (
    <div ref={ref} className="relative w-full overflow-hidden" onMouseLeave={() => setTip(null)}>
      <p className="text-[12.5px] font-semibold text-ink leading-tight">{title}</p>
      {subtitle ? <p className="text-[11.5px] text-ink2 leading-tight mt-0.5">{subtitle}</p> : null}
      <svg width={width} height={height} role="img" aria-label={title} className="mt-1">
        <g transform={`translate(${margin.left},${margin.top})`}>
          {ticks.map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <line x2={innerW} stroke="var(--hairline)" strokeDasharray="2 3" />
              <text x={-6} dy="0.32em" textAnchor="end" className="fill-[var(--ink2)] text-[10.5px] num">
                {formatValue(t, fmt)}
              </text>
            </g>
          ))}
          {reference ? (
            <g>
              <line
                x1={0}
                x2={innerW}
                y1={y(reference.y)}
                y2={y(reference.y)}
                stroke="var(--ink2)"
                strokeWidth={1.5}
                strokeDasharray={reference.y === 0 ? undefined : "4 3"}
              />
            </g>
          ) : null}
          {points.map((p) => {
            const cx = (x(p.key) ?? 0) + x.bandwidth() / 2;
            const show = (e: Parameters<typeof pointIn>[1]) => {
              const at = pointIn(ref.current, e);
              const interval = p.low !== null && p.high !== null ? ` (${formatValue(p.low, fmt)} to ${formatValue(p.high, fmt)})` : "";
              setTip({ x: at.x, y: at.y, lines: [p.label, `${formatValue(p.value, fmt)}${interval}`] });
            };
            return (
              <g key={p.key} tabIndex={0} onMouseMove={show} onFocus={show} onBlur={() => setTip(null)} className="outline-none">
                <rect x={x(p.key) ?? 0} y={0} width={x.bandwidth()} height={innerH} fill="transparent" />
                {p.low !== null && p.high !== null ? (
                  <line x1={cx} x2={cx} y1={y(clamp(p.low))} y2={y(clamp(p.high))} stroke={p.color} strokeWidth={2} />
                ) : null}
                {p.value !== null ? (
                  <circle cx={cx} cy={y(clamp(p.value))} r={4.5} fill={p.color} stroke="var(--chart-bg)" strokeWidth={1.5} />
                ) : null}
                <text x={cx} y={innerH + 14} textAnchor="middle" className="fill-[var(--ink2)] text-[10px]">
                  {p.short}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
