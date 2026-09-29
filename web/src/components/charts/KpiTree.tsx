"use client";

import { scaleLinear } from "d3-scale";
import { useState } from "react";

import { formatValue } from "@/lib/format";

import { Legend } from "./Legend";
import { diamondPath, hbarPath } from "./shapes";
import { pointIn, type Tip, Tooltip } from "./Tooltip";
import { useWidth } from "./useWidth";

export interface KpiLine {
  key: string;
  label: string;
  depth: 0 | 1 | 2;
  value: number | null;
  truth: number | null;
  /** Channel rows carry their color and a bar against the truth. */
  color?: string;
  note?: string;
}

/**
 * The quarter as a tree: sales at the top, the baseline and each channel's incremental sales under
 * it, media spend beside it. Every line prints the estimate beside the simulated truth; channel
 * lines also draw the estimate as a bar and the truth as a hollow diamond on one shared scale.
 */
export function KpiTree({ lines, fmt, estimateLabel, testId }: { lines: KpiLine[]; fmt: string; estimateLabel: string; testId?: string }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [tip, setTip] = useState<Tip | null>(null);
  const barMax = Math.max(...lines.filter((l) => l.color).flatMap((l) => [l.value ?? 0, l.truth ?? 0]), 1);
  // The widest bar leaves room for the deepest indent, so no line pushes the page sideways.
  const x = scaleLinear()
    .domain([0, barMax])
    .nice(4)
    .range([0, Math.max(width - 70, 100)]);
  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setTip(null)} data-testid={testId}>
      <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 text-xs text-ink2 border-b border-hairline pb-1 mb-1">
        <span>Line</span>
        <span className="text-right w-[5.5rem]">{estimateLabel}</span>
        <span className="text-right w-[5.5rem]">Truth (simulated)</span>
      </div>
      <ul>
        {lines.map((l) => {
          const show = (e: Parameters<typeof pointIn>[1]) => {
            const at = pointIn(ref.current, e);
            setTip({
              x: at.x,
              y: at.y,
              lines: [
                l.label,
                `${estimateLabel}: ${formatValue(l.value, fmt)}`,
                l.truth !== null ? `truth (simulated): ${formatValue(l.truth, fmt)}` : "",
                l.note ?? "",
              ],
            });
          };
          return (
            <li
              key={l.key}
              tabIndex={0}
              onMouseMove={show}
              onFocus={show}
              onBlur={() => setTip(null)}
              className={`py-1.5 border-b border-hairline last:border-b-0 outline-none focus-visible:bg-surface ${l.depth === 0 ? "font-semibold" : ""}`}
              data-line={l.key}
            >
              <div className="grid grid-cols-[1fr_auto_auto] gap-x-4 items-baseline">
                <span className="flex items-center gap-2 min-w-0" style={{ paddingLeft: `${l.depth * 1.1}rem` }}>
                  {l.color ? (
                    <span className="inline-block w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: l.color }} aria-hidden="true" />
                  ) : null}
                  <span className="truncate">{l.label}</span>
                </span>
                <span className="num text-right w-[5.5rem]">{formatValue(l.value, fmt)}</span>
                <span className="num text-right w-[5.5rem] text-ink2">{l.truth === null ? "" : formatValue(l.truth, fmt)}</span>
              </div>
              {l.color && l.value !== null ? (
                <svg
                  width={Math.max(width - l.depth * 18, 110)}
                  height={14}
                  className="block mt-1"
                  style={{ marginLeft: `${l.depth * 1.1}rem` }}
                  aria-hidden="true"
                >
                  <path d={hbarPath(0, x(l.value), 3, 8)} fill={l.color} />
                  {l.truth !== null ? (
                    <path d={diamondPath(x(l.truth), 7, 5.5)} fill="none" stroke="var(--ink)" strokeWidth={1.5} data-truth-marker />
                  ) : null}
                </svg>
              ) : null}
            </li>
          );
        })}
      </ul>
      <Legend
        items={[
          { label: `${estimateLabel}, incremental sales`, color: "var(--ink2)", kind: "bar" },
          { label: "truth (simulated)", color: "var(--ink)", kind: "diamond" },
        ]}
      />
      <Tooltip tip={tip} width={width} />
    </div>
  );
}
