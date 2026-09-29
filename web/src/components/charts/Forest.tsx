"use client";

import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { Legend, type LegendItem } from "./Legend";
import { diamondPath, wrapLabel } from "./shapes";
import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { fitTicks, textWidth, useWidth } from "./useWidth";

export interface ForestRow {
  key: string;
  label: string;
  color: string;
  estimate: number | null;
  low?: number | null;
  high?: number | null;
  truth?: number | null;
  /** A second line for the tooltip, such as whether the interval covers the truth. */
  note?: string;
}

/**
 * One row per item on one horizontal axis: the interval as a 2px line, the estimate as a filled
 * circle in the row's color, the simulated truth as a small hollow diamond in ink.
 */
export function Forest({
  rows,
  fmt,
  axisLabel,
  reference,
  estimateLabel = "estimate",
  intervalLabel,
  truthLabel = "truth (simulated)",
  testId,
}: {
  rows: ForestRow[];
  fmt: string;
  axisLabel: string;
  reference?: { value: number; label: string };
  estimateLabel?: string;
  intervalLabel?: string;
  truthLabel?: string;
  testId?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const labelW = Math.round(Math.min(190, Math.max(104, width * 0.32)));
  const chars = Math.floor(labelW / 7);
  const right = 18;
  const rowH = 34;
  const top = 8;
  const axisH = 38;
  const values = rows
    .flatMap((r) => [r.estimate, r.low ?? null, r.high ?? null, r.truth ?? null])
    .filter((v): v is number => v !== null && Number.isFinite(v));
  if (reference) values.push(reference.value);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const pad = (hi - lo) * 0.06 || Math.abs(hi) * 0.1 || 1;
  // A scale of returns or dollars that never goes below zero does not start below zero either.
  const domain = scaleLinear()
    .domain([lo >= 0 ? Math.max(0, lo - pad) : lo - pad, hi + pad])
    .nice(5)
    .domain();
  // Room at the right for half of the widest tick label, so the last one is never cut off.
  const edge = Math.max(right, textWidth(formatValue(domain[1] ?? 0, fmt), 11) / 2 + 4);
  const x = scaleLinear()
    .domain(domain)
    .range([labelW + 8, Math.max(width - edge, labelW + 120)]);
  const ticks = fitTicks(x, Math.max(width - edge - labelW - 8, 60), (t) => formatValue(t, fmt), width < 480 ? 4 : 6);
  const height = top + rows.length * rowH + axisH;
  const hasTruth = rows.some((r) => r.truth !== null && r.truth !== undefined);
  const hasInterval = rows.some((r) => r.low !== null && r.low !== undefined);

  const legend: LegendItem[] = [
    {
      label: hasInterval ? `${estimateLabel}, ${intervalLabel ?? "with its interval"}` : estimateLabel,
      color: "var(--ink2)",
      kind: hasInterval ? "interval" : "dot",
    },
  ];
  if (hasTruth) legend.push({ label: truthLabel, color: "var(--ink)", kind: "diamond" });
  if (reference) legend.push({ label: reference.label, color: "var(--control)", kind: "rule", dash: "4 3" });

  return (
    <div ref={ref} className="relative w-full overflow-hidden" onMouseLeave={() => setTip(null)} data-testid={testId}>
      <svg width={width} height={height} role="img" aria-label={axisLabel}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top} y2={height - axisH + 4} stroke="var(--hairline)" />
            <text x={x(t)} y={height - axisH + 18} textAnchor="middle" className="fill-[var(--ink2)] text-[11px] num">
              {formatValue(t, fmt)}
            </text>
          </g>
        ))}
        <text x={(labelW + width - edge) / 2} y={height - 4} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
          {axisLabel}
        </text>
        {reference ? (
          <line
            x1={x(reference.value)}
            x2={x(reference.value)}
            y1={top - 4}
            y2={height - axisH + 4}
            stroke="var(--control)"
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        ) : null}
        {rows.map((r, i) => {
          const y = top + i * rowH + rowH / 2;
          const lines = wrapLabel(r.label, chars);
          const show = (e: Parameters<typeof pointIn>[1]) => {
            const at = pointIn(ref.current, e);
            const interval =
              r.low !== null && r.low !== undefined && r.high !== null && r.high !== undefined
                ? ` (${formatValue(r.low, fmt)} to ${formatValue(r.high, fmt)})`
                : "";
            setTip({
              x: at.x,
              y: at.y,
              lines: [
                r.label,
                `${estimateLabel}: ${formatValue(r.estimate, fmt)}${interval}`,
                r.truth !== null && r.truth !== undefined ? `${truthLabel}: ${formatValue(r.truth, fmt)}` : "",
                r.note ?? "",
              ],
            });
          };
          return (
            <g
              key={r.key}
              tabIndex={0}
              onMouseMove={show}
              onFocus={show}
              onBlur={() => setTip(null)}
              data-row={r.key}
              className="outline-none"
            >
              <rect x={0} y={y - rowH / 2} width={width} height={rowH} fill="transparent" />
              <text x={0} y={y} className="fill-[var(--ink)] text-[12.5px]">
                {lines.map((line, k) => (
                  <tspan key={k} x={0} dy={k === 0 ? (lines.length > 1 ? "-0.2em" : "0.35em") : "1.15em"}>
                    {line}
                  </tspan>
                ))}
              </text>
              {r.low !== null && r.low !== undefined && r.high !== null && r.high !== undefined ? (
                <g stroke={r.color} strokeWidth={2}>
                  <line x1={x(r.low)} x2={x(r.high)} y1={y} y2={y} />
                  <line x1={x(r.low)} x2={x(r.low)} y1={y - 4} y2={y + 4} />
                  <line x1={x(r.high)} x2={x(r.high)} y1={y - 4} y2={y + 4} />
                </g>
              ) : null}
              {r.estimate !== null ? (
                <circle cx={x(r.estimate)} cy={y} r={5} fill={r.color} stroke="var(--chart-bg)" strokeWidth={1.5} />
              ) : null}
              {r.truth !== null && r.truth !== undefined ? (
                <path d={diamondPath(x(r.truth), y, 6)} fill="none" stroke="var(--ink)" strokeWidth={1.5} data-truth-marker />
              ) : null}
            </g>
          );
        })}
      </svg>
      <Legend items={legend} />
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
