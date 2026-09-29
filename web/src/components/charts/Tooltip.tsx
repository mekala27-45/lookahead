"use client";

import type { FocusEvent, MouseEvent, PointerEvent } from "react";

export interface Tip {
  x: number;
  y: number;
  lines: string[];
}

const WIDTH = 230;

export function Tooltip({ tip, width }: { tip: Tip | null; width: number }) {
  if (!tip) return null;
  const left = Math.max(0, Math.min(tip.x + 14, width - WIDTH));
  return (
    <div
      role="status"
      className="pointer-events-none absolute z-20 rounded border border-hairline bg-raised px-2.5 py-1.5 text-xs text-ink shadow-md"
      style={{ left, top: Math.max(tip.y - 10, 0), maxWidth: WIDTH }}
    >
      {tip.lines
        .filter((line) => line !== "")
        .map((line, i) => (
          <div key={i} className={i === 0 ? "font-semibold" : "num"}>
            {line}
          </div>
        ))}
    </div>
  );
}

/** Where a pointer or focus event lands inside a chart's container, for placing its tooltip. */
export function pointIn(
  container: HTMLElement | null,
  event: MouseEvent<Element> | PointerEvent<Element> | FocusEvent<Element>,
): { x: number; y: number } {
  if (!container) return { x: 0, y: 0 };
  const box = container.getBoundingClientRect();
  if ("clientX" in event && (event.clientX !== 0 || event.clientY !== 0)) {
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  }
  const target = (event.currentTarget as Element).getBoundingClientRect();
  return { x: target.left + target.width / 2 - box.left, y: target.top - box.top };
}
