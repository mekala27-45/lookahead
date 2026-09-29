"use client";

import { useState } from "react";

import { formatValue } from "@/lib/format";

import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { useWidth } from "./useWidth";

const RAMP = ["var(--seq-1)", "var(--seq-2)", "var(--seq-3)", "var(--seq-4)", "var(--seq-5)"];

/**
 * A matrix on the sequential plum ramp, linear from zero to one. Every cell prints its value, so
 * the color is never the only way to read it.
 */
export function Heatmap({
  rows,
  columns,
  cells,
  fmt,
  rowLabel,
  columnLabel,
  testId,
}: {
  rows: string[];
  columns: string[];
  /** cells[i][j] is the value for rows[i] and columns[j]; null is an empty cell. */
  cells: (number | null)[][];
  fmt: string;
  rowLabel: string;
  columnLabel: string;
  testId?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const left = Math.min(110, Math.max(84, width * 0.24));
  const top = 36;
  const cellW = Math.max((width - left - 4) / columns.length, 58);
  const cellH = 38;
  const step = (v: number) => Math.min(RAMP.length - 1, Math.max(0, Math.floor(v * RAMP.length - 1e-9)));
  return (
    <div ref={ref} className="relative w-full overflow-x-auto" onMouseLeave={() => setTip(null)} data-testid={testId}>
      <svg
        width={left + cellW * columns.length + 4}
        height={top + cellH * rows.length + 6}
        role="img"
        aria-label={`${columnLabel} by ${rowLabel}`}
      >
        <text x={left} y={12} className="fill-[var(--ink2)] text-[11px]">
          {columnLabel}
        </text>
        {columns.map((c, j) => (
          <text key={c} x={left + j * cellW + cellW / 2} y={29} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
            {c}
          </text>
        ))}
        {rows.map((r, i) => (
          <g key={r}>
            <text x={left - 8} y={top + i * cellH + cellH / 2} dy="0.32em" textAnchor="end" className="fill-[var(--ink)] text-[12px]">
              {r}
            </text>
            {columns.map((c, j) => {
              const v = cells[i]?.[j] ?? null;
              const k = v === null ? -1 : step(v);
              const show = (e: Parameters<typeof pointIn>[1]) => {
                const at = pointIn(ref.current, e);
                setTip({ x: at.x, y: at.y, lines: [`${r}, ${c}`, formatValue(v, fmt)] });
              };
              return (
                <g key={c} tabIndex={0} onMouseMove={show} onFocus={show} onBlur={() => setTip(null)} className="outline-none">
                  <rect
                    x={left + j * cellW + 1}
                    y={top + i * cellH + 1}
                    width={cellW - 2}
                    height={cellH - 2}
                    rx={3}
                    fill={k < 0 ? "var(--surface)" : RAMP[k]}
                  />
                  <text
                    x={left + j * cellW + cellW / 2}
                    y={top + i * cellH + cellH / 2}
                    dy="0.32em"
                    textAnchor="middle"
                    className="text-[11.5px] num"
                    fill={k >= 2 ? "var(--surface)" : "var(--ink)"}
                  >
                    {v === null ? "" : formatValue(v, fmt)}
                  </text>
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
