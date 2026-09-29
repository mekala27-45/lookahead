"use client";

import { scaleLinear } from "d3-scale";
import { area, line } from "d3-shape";
import { type KeyboardEvent, useMemo, useState } from "react";

import { formatValue } from "@/lib/format";

import { Legend, type LegendItem } from "./Legend";
import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { fitTicks, textWidth, useWidth } from "./useWidth";

export interface StackLayer {
  key: string;
  label: string;
  color: string;
  /** A texture drawn over the fill, such as the baseline's hatch. */
  pattern?: string;
}
export interface StackRow {
  x: number;
  values: Record<string, number>;
  total: number | null;
}

/**
 * Layers stacked from the bottom in the order given, each separated from the next by a 2px gap
 * in the chart's own background, with a total drawn as a line on top.
 */
export function StackedArea({
  rows,
  layers,
  totalLabel,
  xFmt,
  yFmt,
  xLabel,
  yLabel,
  height = 320,
  testId,
}: {
  rows: StackRow[];
  layers: StackLayer[];
  totalLabel: string;
  xFmt: string;
  yFmt: string;
  xLabel: string;
  yLabel: string;
  height?: number;
  testId?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  const stacked = useMemo(
    () =>
      rows.map((r) => {
        let run = 0;
        const bands: Record<string, [number, number]> = {};
        for (const layer of layers) {
          const v = Math.max(r.values[layer.key] ?? 0, 0);
          bands[layer.key] = [run, run + v];
          run += v;
        }
        return { x: r.x, bands, top: run, total: r.total };
      }),
    [rows, layers],
  );
  const hi = Math.max(...stacked.map((s) => Math.max(s.top, s.total ?? 0)), 1);
  const y0 = scaleLinear().domain([0, hi]).nice(5);
  const ticks = y0.ticks(5);
  const lastX = rows[rows.length - 1]?.x ?? 0;
  const margin = {
    top: 12,
    right: Math.max(12, textWidth(formatValue(lastX, xFmt), 11) / 2 + 4),
    bottom: 42,
    left: Math.ceil(Math.max(...ticks.map((t) => textWidth(formatValue(t, yFmt), 11)))) + 12,
  };
  const innerW = Math.max(width - margin.left - margin.right, 80);
  const innerH = height - margin.top - margin.bottom;
  const y = y0.range([innerH, 0]);
  const xLo = stacked[0]?.x ?? 0;
  const xHi = stacked[stacked.length - 1]?.x ?? 1;
  const x = scaleLinear().domain([xLo, xHi]).range([0, innerW]);
  const xTicks = fitTicks(x, innerW, (t) => formatValue(t, xFmt), width < 480 ? 4 : 8);

  const totalPath = line<(typeof stacked)[number]>()
    .defined((d) => d.total !== null)
    .x((d) => x(d.x))
    .y((d) => y(d.total ?? 0));

  const showAt = (index: number, px?: number, py?: number) => {
    const s = stacked[index];
    const row = rows[index];
    if (!s || !row) return;
    setHover(index);
    const lines = [`${xLabel} ${formatValue(s.x, xFmt)}`, `${totalLabel}: ${formatValue(s.total, yFmt)}`];
    for (const layer of [...layers].reverse()) lines.push(`${layer.label}: ${formatValue(row.values[layer.key] ?? null, yFmt)}`);
    setTip({ x: px ?? x(s.x) + margin.left, y: py ?? margin.top, lines });
  };
  const onMove = (e: Parameters<typeof pointIn>[1]) => {
    const at = pointIn(ref.current, e);
    const value = x.invert(at.x - margin.left);
    let index = 0;
    let gap = Infinity;
    stacked.forEach((s, i) => {
      const d = Math.abs(s.x - value);
      if (d < gap) {
        gap = d;
        index = i;
      }
    });
    showAt(index, at.x, Math.min(at.y, height - 200));
  };
  const onKey = (e: KeyboardEvent<SVGRectElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const step = e.key === "ArrowRight" ? 1 : -1;
      showAt(Math.min(Math.max((hover ?? (step > 0 ? -1 : stacked.length)) + step, 0), stacked.length - 1));
    } else if (e.key === "Escape") {
      setHover(null);
      setTip(null);
    }
  };

  const legend: LegendItem[] = [
    ...layers.map((l) => ({ label: l.label, color: l.color, kind: "bar" as const, pattern: l.pattern })),
    { label: totalLabel, color: "var(--ink)", kind: "line" },
  ];
  const hoverRow = hover !== null ? stacked[hover] : undefined;

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
      <p className="text-[11px] text-ink2 mb-1">{yLabel}</p>
      <svg width={width} height={height} role="img" aria-label={`${yLabel} by ${xLabel}`}>
        <g transform={`translate(${margin.left},${margin.top})`}>
          {ticks.map((t) => (
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
          <text x={innerW / 2} y={innerH + 34} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
            {xLabel}
          </text>
          {layers.map((layer) => {
            const shape = area<(typeof stacked)[number]>()
              .x((d) => x(d.x))
              .y0((d) => y(d.bands[layer.key]?.[0] ?? 0))
              .y1((d) => y(d.bands[layer.key]?.[1] ?? 0));
            const d = shape(stacked) ?? "";
            return (
              <g key={layer.key} data-layer={layer.key}>
                <path d={d} fill={layer.color} stroke="var(--chart-bg)" strokeWidth={2} strokeLinejoin="round" />
                {layer.pattern ? <path d={d} fill={layer.pattern} stroke="var(--chart-bg)" strokeWidth={2} strokeLinejoin="round" /> : null}
              </g>
            );
          })}
          <path d={totalPath(stacked) ?? ""} fill="none" stroke="var(--ink)" strokeWidth={2} strokeLinejoin="round" />
          {hoverRow ? (
            <line x1={x(hoverRow.x)} x2={x(hoverRow.x)} y1={0} y2={innerH} stroke="var(--ink)" strokeWidth={1} pointerEvents="none" />
          ) : null}
          <rect
            x={0}
            y={0}
            width={innerW}
            height={innerH}
            fill="transparent"
            tabIndex={0}
            aria-label={`Read ${yLabel} week by week; use the arrow keys`}
            onMouseMove={onMove}
            onKeyDown={onKey}
            onBlur={() => {
              setHover(null);
              setTip(null);
            }}
            className="outline-none"
          />
        </g>
      </svg>
      <Legend items={legend} />
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
