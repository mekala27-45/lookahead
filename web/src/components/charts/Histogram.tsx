"use client";

import { bin } from "d3-array";
import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { PATTERN } from "./Defs";
import { Legend, type LegendItem } from "./Legend";
import { diamondPath, vbarPath } from "./shapes";
import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { fitTicks, textWidth, useWidth } from "./useWidth";

export interface Rule {
  x: number;
  label: string;
  color: string;
  dash?: string;
}

/**
 * A distribution as a histogram in the control gray, with estimates as vertical rules and the
 * truth as a hollow diamond on the axis: the effect set against what chance produces.
 */
export function Histogram({
  values,
  fmt,
  xLabel,
  yLabel,
  rules = [],
  truth,
  distributionLabel,
  height = 260,
  testId,
}: {
  values: number[];
  fmt: string;
  xLabel: string;
  yLabel: string;
  rules?: Rule[];
  truth?: { x: number; label: string };
  distributionLabel: string;
  height?: number;
  testId?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const all = [...values, ...rules.map((r) => r.x), ...(truth ? [truth.x] : [])];
  const lo = Math.min(...all);
  const hi = Math.max(...all);
  const pad = (hi - lo) * 0.04 || 1;
  const x0 = scaleLinear()
    .domain([lo - pad, hi + pad])
    .nice(6);
  const bins = bin()
    .domain(x0.domain() as [number, number])
    .thresholds(x0.ticks(28))(values);
  const counts = bins.map((b) => b.length);
  const y0 = scaleLinear()
    .domain([0, Math.max(...counts, 1)])
    .nice(4);
  const yTicks = y0.ticks(4);
  // Room at the right for half of the last tick label, so it is never cut off.
  const right = Math.max(16, textWidth(formatValue(x0.domain()[1] ?? 0, fmt), 11) / 2 + 4);
  const margin = { top: 34, right, bottom: 42, left: Math.ceil(Math.max(...yTicks.map((t) => textWidth(formatValue(t, "int"), 11)))) + 14 };
  const innerW = Math.max(width - margin.left - margin.right, 100);
  const innerH = height - margin.top - margin.bottom;
  const x = x0.range([0, innerW]);
  const y = y0.range([innerH, 0]);
  const xTicks = fitTicks(x, innerW, (t) => formatValue(t, fmt), width < 480 ? 4 : 6);

  const legend: LegendItem[] = [
    { label: distributionLabel, color: "transparent", kind: "bar", pattern: PATTERN.placebo },
    ...rules.map((r) => ({ label: r.label, color: r.color, kind: "rule" as const, dash: r.dash })),
  ];
  if (truth) legend.push({ label: truth.label, color: "var(--ink)", kind: "diamond" });

  return (
    <div ref={ref} className="relative w-full overflow-hidden" onMouseLeave={() => setTip(null)} data-testid={testId}>
      <p className="text-[11px] text-ink2 mb-1">Number of {yLabel}</p>
      <svg width={width} height={height} role="img" aria-label={`${yLabel} by ${xLabel}`}>
        <g transform={`translate(${margin.left},${margin.top})`}>
          {yTicks.map((t) => (
            <g key={t} transform={`translate(0,${y(t)})`}>
              <line x2={innerW} stroke="var(--hairline)" strokeDasharray={t === 0 ? undefined : "2 3"} />
              <text x={-8} dy="0.32em" textAnchor="end" className="fill-[var(--ink2)] text-[11px] num">
                {formatValue(t, "int")}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={innerH + 17} textAnchor="middle" className="fill-[var(--ink2)] text-[11px] num">
              {formatValue(t, fmt)}
            </text>
          ))}
          <text x={innerW / 2} y={innerH + 34} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
            {xLabel}
          </text>
          {bins.map((b, i) => {
            if (b.length === 0 || b.x0 === undefined || b.x1 === undefined) return null;
            const left = x(b.x0) + 1;
            const w = Math.max(x(b.x1) - x(b.x0) - 2, 1);
            const d = vbarPath(left, w, y(0), y(b.length));
            const show = (e: Parameters<typeof pointIn>[1]) => {
              const at = pointIn(ref.current, e);
              setTip({
                x: at.x,
                y: at.y,
                lines: [
                  distributionLabel,
                  `${formatValue(b.x0 ?? null, fmt)} to ${formatValue(b.x1 ?? null, fmt)}`,
                  `${formatValue(b.length, "int")} ${yLabel}`,
                ],
              });
            };
            return (
              <g key={i} tabIndex={0} onMouseMove={show} onFocus={show} onBlur={() => setTip(null)} className="outline-none">
                <path d={d} fill={PATTERN.placebo} />
              </g>
            );
          })}
          {rules.map((r, i) => {
            const show = (e: Parameters<typeof pointIn>[1]) => {
              const at = pointIn(ref.current, e);
              setTip({ x: at.x, y: at.y, lines: [r.label, formatValue(r.x, fmt)] });
            };
            return (
              <g
                key={r.label}
                onMouseMove={show}
                tabIndex={0}
                onFocus={show}
                onBlur={() => setTip(null)}
                className="outline-none"
                data-rule={r.label}
              >
                <line x1={x(r.x)} x2={x(r.x)} y1={-6 - i * 12} y2={innerH} stroke={r.color} strokeWidth={2} strokeDasharray={r.dash} />
                <line x1={x(r.x)} x2={x(r.x)} y1={-6 - i * 12} y2={innerH} stroke="transparent" strokeWidth={10} />
                <text x={x(r.x) - 5} y={-10 - i * 12} textAnchor="end" className="fill-[var(--ink2)] text-[10.5px]">
                  {r.label}
                </text>
              </g>
            );
          })}
          {truth ? (
            <g
              tabIndex={0}
              onMouseMove={(e) => {
                const at = pointIn(ref.current, e);
                setTip({ x: at.x, y: at.y, lines: [truth.label, formatValue(truth.x, fmt)] });
              }}
              onMouseLeave={() => setTip(null)}
              className="outline-none"
            >
              <path
                d={diamondPath(x(truth.x), innerH - 8, 7)}
                fill="var(--chart-bg)"
                stroke="var(--ink)"
                strokeWidth={1.5}
                data-truth-marker
              />
            </g>
          ) : null}
        </g>
      </svg>
      <Legend items={legend} />
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
