import { diamondPath } from "./shapes";

export interface LegendItem {
  label: string;
  color: string;
  kind: "line" | "bar" | "dot" | "diamond" | "rule" | "interval";
  dash?: string;
  pattern?: string;
  opacity?: number;
}

function Swatch({ item }: { item: LegendItem }) {
  const { color, kind } = item;
  return (
    <svg width="20" height="12" aria-hidden="true" className="shrink-0">
      {kind === "line" ? (
        <line x1="0" x2="20" y1="6" y2="6" stroke={color} strokeWidth="2" strokeDasharray={item.dash} opacity={item.opacity} />
      ) : null}
      {kind === "rule" ? <line x1="10" x2="10" y1="0" y2="12" stroke={color} strokeWidth="2" strokeDasharray={item.dash} /> : null}
      {kind === "bar" ? (
        <>
          <rect x="1" y="2" width="18" height="8" rx="2" fill={color} opacity={item.opacity} />
          {item.pattern ? <rect x="1" y="2" width="18" height="8" rx="2" fill={item.pattern} /> : null}
        </>
      ) : null}
      {kind === "dot" ? <circle cx="10" cy="6" r="4.5" fill={color} /> : null}
      {kind === "interval" ? (
        <>
          <line x1="2" x2="18" y1="6" y2="6" stroke={color} strokeWidth="2" />
          <circle cx="10" cy="6" r="4" fill={color} />
        </>
      ) : null}
      {kind === "diamond" ? <path d={diamondPath(10, 6, 5)} fill="none" stroke={color} strokeWidth="1.5" /> : null}
    </svg>
  );
}

/** A legend, shown whenever a chart has two or more series or marks. */
export function Legend({ items, label = "Legend" }: { items: LegendItem[]; label?: string }) {
  if (items.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink2 mt-2" aria-label={label}>
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5" data-legend-item={item.label}>
          <Swatch item={item} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
