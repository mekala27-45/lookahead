"use client";

import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { Legend } from "./Legend";
import { hbarPath, wrapLabel } from "./shapes";
import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { textWidth, useWidth } from "./useWidth";

/**
 * Horizontal bars either side of zero on the diverging ramp: plum for a gain, teal for a loss,
 * the value printed at the end of each bar.
 */
export function Diverging({
  items,
  fmt,
  axisLabel,
  positiveLabel,
  negativeLabel,
  testId,
}: {
  items: { key: string; label: string; value: number; note?: string }[];
  fmt: string;
  axisLabel: string;
  positiveLabel: string;
  negativeLabel: string;
  testId?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const labelW = Math.round(Math.min(180, Math.max(96, width * 0.3)));
  const chars = Math.floor(labelW / 7);
  const valueW = Math.max(...items.map((d) => textWidth(formatValue(d.value, fmt), 11))) + 10;
  const rowH = 34;
  const max = Math.max(...items.map((d) => Math.abs(d.value)), 1e-9);
  const x = scaleLinear()
    .domain([-max, max])
    .range([labelW + valueW, Math.max(width - valueW, labelW + valueW + 80)]);
  const zero = x(0);
  const height = items.length * rowH + 30;
  return (
    <div ref={ref} className="relative w-full overflow-hidden" onMouseLeave={() => setTip(null)} data-testid={testId}>
      <svg width={width} height={height} role="img" aria-label={axisLabel}>
        <line x1={zero} x2={zero} y1={0} y2={height - 24} stroke="var(--ink2)" />
        <text x={width / 2} y={height - 8} textAnchor="middle" className="fill-[var(--ink2)] text-[11px]">
          {axisLabel}
        </text>
        {items.map((d, i) => {
          const end = x(d.value);
          const negative = d.value < 0;
          const y = i * rowH + 6;
          const lines = wrapLabel(d.label, chars);
          const show = (e: Parameters<typeof pointIn>[1]) => {
            const at = pointIn(ref.current, e);
            setTip({ x: at.x, y: at.y, lines: [d.label, formatValue(d.value, fmt), d.note ?? ""] });
          };
          return (
            <g key={d.key} tabIndex={0} onMouseMove={show} onFocus={show} onBlur={() => setTip(null)} className="outline-none">
              <rect x={0} y={y - 4} width={width} height={rowH} fill="transparent" />
              <text x={0} y={y + (rowH - 12) / 2} className="fill-[var(--ink)] text-[12.5px]">
                {lines.map((line, k) => (
                  <tspan key={k} x={0} dy={k === 0 ? (lines.length > 1 ? "-0.2em" : "0.35em") : "1.15em"}>
                    {line}
                  </tspan>
                ))}
              </text>
              <path d={hbarPath(zero, end, y + 2, rowH - 16)} fill={negative ? "var(--div-2)" : "var(--div-8)"} />
              <text
                x={negative ? end - 5 : end + 5}
                y={y + (rowH - 12) / 2}
                dy="0.35em"
                textAnchor={negative ? "end" : "start"}
                className="fill-[var(--ink)] text-[11px] num"
              >
                {formatValue(d.value, fmt)}
              </text>
            </g>
          );
        })}
      </svg>
      <Legend
        items={[
          { label: positiveLabel, color: "var(--div-8)", kind: "bar" },
          { label: negativeLabel, color: "var(--div-2)", kind: "bar" },
        ]}
      />
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
