"use client";

import { type RefObject, useEffect, useRef, useState } from "react";

/** The width of a container, kept current as it resizes. Charts draw in pixels, not a viewBox, so text stays its size. */
export function useWidth<T extends HTMLElement>(initial = 640): [RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(initial);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const measure = (w: number) => setWidth((prev) => (w > 0 && Math.abs(prev - w) > 1 ? Math.floor(w) : prev));
    measure(node.getBoundingClientRect().width);
    const observer = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) measure(w);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

/** Line dash patterns, one per series slot, so lines differ in texture as well as hue. */
export const DASHES = ["", "7 3", "2 3", "9 3 2 3", "1 3", "12 4", "4 4", "3 6"];

/** Approximate rendered width of interface text, for sizing margins before the browser measures. */
export function textWidth(text: string, px = 12): number {
  return text.length * px * 0.6;
}

/**
 * Ticks for an axis, thinned until their printed labels fit side by side: a dollar axis on a
 * phone gets fewer ticks than a share axis on a desktop.
 */
export function fitTicks(scale: { ticks: (count?: number) => number[] }, span: number, label: (t: number) => string, start = 6): number[] {
  let count = start;
  let ticks = scale.ticks(count);
  const widest = (ts: number[]) => Math.max(0, ...ts.map((t) => textWidth(label(t), 11)));
  while (count > 1 && ticks.length > 2 && span / (ticks.length - 1) < widest(ticks) * 1.25 + 12) {
    count -= 1;
    ticks = scale.ticks(count);
  }
  return ticks;
}
