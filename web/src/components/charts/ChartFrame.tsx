"use client";

import { type ReactNode, useId, useState } from "react";

import { formatValue, type Scalar } from "@/lib/format";

export interface TableData {
  columns: string[];
  formats: string[];
  /** A missing cell (undefined) prints as a null would. */
  rows: (Scalar | undefined)[][];
}

/**
 * Every chart: a title, a table toggle beside it, the chart or its table, one written callout
 * whose figures come from the manifest, and the provenance line of the entry it is drawn from.
 */
export function ChartFrame({
  title,
  callout,
  provenance,
  table,
  children,
  controls,
  testId,
  wide = false,
}: {
  title: string;
  callout: ReactNode;
  provenance: string;
  table: TableData | null;
  children: ReactNode;
  controls?: ReactNode;
  testId?: string;
  wide?: boolean;
}) {
  const [showTable, setShowTable] = useState(false);
  const id = useId();
  return (
    <figure className={`card chart p-4 sm:p-5 min-w-0 ${wide ? "lg:col-span-2" : ""}`} aria-labelledby={id} data-testid={testId}>
      <div className="flex items-start justify-between gap-3 mb-3">
        <h3 id={id} className="font-sans text-[0.95rem] font-semibold text-ink leading-snug">
          {title}
        </h3>
        <button
          type="button"
          onClick={() => setShowTable((s) => !s)}
          className="no-print text-xs px-2 py-1 border border-hairline rounded text-ink2 hover:text-ink hover:border-control shrink-0"
          aria-pressed={showTable}
          data-testid="table-toggle"
        >
          {showTable ? "Show chart" : "Show table"}
        </button>
      </div>
      {controls ? <div className="mb-3">{controls}</div> : null}
      {showTable ? <DataTable table={table} /> : children}
      <figcaption className="mt-3 text-sm text-ink leading-relaxed prose">{callout}</figcaption>
      <p className="mt-1.5 text-xs text-ink2 leading-snug">{provenance}</p>
    </figure>
  );
}

export function DataTable({
  table,
  max = 400,
  dense = true,
  caption,
  label,
}: {
  table: TableData | null;
  max?: number;
  dense?: boolean;
  /** A visible caption; `label` names the table for screen readers without one. */
  caption?: string;
  label?: string;
}) {
  if (!table) {
    return (
      <div className="overflow-x-auto" role="region" aria-label="Chart data" tabIndex={0}>
        <table className="data-table dense">
          <tbody>
            <tr>
              <td className="text-ink2">The data is still loading.</td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }
  const rows = table.rows.slice(0, max);
  return (
    <div className="overflow-x-auto max-h-[440px] overflow-y-auto" role="region" aria-label={caption ?? label ?? "Chart data"} tabIndex={0}>
      <table className={`data-table ${dense ? "dense" : ""}`}>
        {caption ? <caption>{caption}</caption> : null}
        <thead>
          <tr>
            {table.columns.map((c, i) => (
              <th key={`${c}-${i}`} scope="col" className={table.formats[i] === "text" ? "" : "num"}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              {row.map((cell, i) => (
                <td key={i} className={table.formats[i] === "text" ? "" : "num"}>
                  {formatValue(cell, table.formats[i] ?? "text")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {table.rows.length > max ? (
        <p className="text-xs text-ink2 mt-2">
          First {formatValue(max, "int")} of {formatValue(table.rows.length, "int")} rows.
        </p>
      ) : null}
    </div>
  );
}

/** A loading state in the shape of the chart it stands in for. */
export function ChartSkeleton({
  shape,
  height = 240,
  rows = 7,
}: {
  shape: "bars" | "lines" | "forest" | "area" | "grid" | "table";
  height?: number;
  rows?: number;
}) {
  const widths = [0.82, 0.64, 0.48, 0.7, 0.36, 0.56, 0.42, 0.74, 0.5, 0.6];
  return (
    <div aria-busy="true" aria-label="Loading the chart" role="img" style={{ minHeight: height }} data-skeleton={shape}>
      {shape === "bars" || shape === "forest" || shape === "table" ? (
        <div className="space-y-3 pt-1">
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="flex items-center gap-3">
              <div className="skeleton h-3 w-24 shrink-0" />
              {shape === "forest" ? (
                <div className="relative flex-1 h-3">
                  <div
                    className="skeleton absolute h-1 top-1"
                    style={{ left: `${18 + ((i * 7) % 20)}%`, width: `${30 + ((i * 11) % 25)}%` }}
                  />
                  <div className="skeleton absolute h-3 w-3 rounded-full" style={{ left: `${35 + ((i * 13) % 25)}%` }} />
                </div>
              ) : (
                <div className="skeleton h-3" style={{ width: `${(widths[i % widths.length] ?? 0.5) * 70}%` }} />
              )}
            </div>
          ))}
        </div>
      ) : null}
      {shape === "lines" || shape === "area" ? (
        <div className="relative w-full" style={{ height }}>
          {[0.2, 0.4, 0.6, 0.8].map((t) => (
            <div key={t} className="absolute left-10 right-2 border-t border-hairline" style={{ top: `${t * 100}%` }} />
          ))}
          <div className={`skeleton absolute left-10 right-2 bottom-6 ${shape === "area" ? "top-[30%]" : "top-[45%] h-1.5"}`} />
        </div>
      ) : null}
      {shape === "grid" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
          {Array.from({ length: rows }, (_, i) => (
            <div key={i} className="skeleton" style={{ height: height / 2 }} />
          ))}
        </div>
      ) : null}
      <span className="sr-only">Loading the chart</span>
    </div>
  );
}
