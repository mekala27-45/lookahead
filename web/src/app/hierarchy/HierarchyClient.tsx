"use client";

import { useEffect, useMemo } from "react";

import { ChartFrame } from "@/components/charts/ChartFrame";
import { GroupedBars } from "@/components/charts/GroupedBars";
import { fmt } from "@/lib/format";
import type { AuthorityInfo, RegionInfo } from "@/lib/load";
import { markReady } from "@/lib/ready";
import { useMart } from "@/lib/useMart";

interface NodeRow extends Record<string, unknown> {
  method: string;
  level: number;
  node: string;
  mape: number | null;
}
interface LevelRow extends Record<string, unknown> {
  method: string;
  level: number;
  level_name: string;
  nodes: number;
  rows: number;
  mape: number;
  mape_lower: number;
  mape_upper: number;
  coverage_90: number;
}

const METHODS = ["base", "bottom_up", "top_down", "mint"] as const;
const METHOD_LABEL: Record<string, string> = { base: "Base (no reconciliation)", bottom_up: "Bottom up", top_down: "Top down", mint: "MinT with shrinkage" };
const METHOD_COLOR: Record<string, string> = { base: "var(--control)", bottom_up: "var(--cat-3)", top_down: "var(--cat-4)", mint: "var(--lead)" };

function Bar({ value, max, color }: { value: number | null; max: number; color: string }) {
  if (value === null || !Number.isFinite(value)) return <span className="text-xs text-ink2">n/a</span>;
  return (
    <span className="inline-flex items-center gap-1.5 w-full">
      <span className="inline-block h-2 rounded-sm" style={{ width: `${Math.min(100, (100 * value) / max)}%`, background: color, minWidth: 2 }} />
      <span className="num text-xs">{fmt(value, "pct1")}</span>
    </span>
  );
}

export function HierarchyClient({
  authorities,
  regions,
  treeCallout,
  treeProvenance,
  levelsCallout,
  levelsProvenance,
}: {
  authorities: AuthorityInfo[];
  regions: RegionInfo[];
  treeCallout: string;
  treeProvenance: string;
  levelsCallout: string;
  levelsProvenance: string;
}) {
  const nodes = useMart<NodeRow>(`select method, level, node, mape from mart_hierarchy_nodes where method in ('base', 'mint') order by level, node`);
  const levels = useMart<LevelRow>(`select * from mart_hierarchy_levels order by level, method`);
  useEffect(() => {
    if (nodes.rows || nodes.error) markReady();
  }, [nodes.rows, nodes.error]);
  const mape = useMemo(() => {
    const map = new Map<string, { base: number | null; mint: number | null; level: number }>();
    for (const r of nodes.rows ?? []) {
      const entry = map.get(r.node) ?? { base: null, mint: null, level: Number(r.level) };
      if (r.method === "base") entry.base = r.mape;
      if (r.method === "mint") entry.mint = r.mape;
      map.set(r.node, entry);
    }
    return map;
  }, [nodes.rows]);
  const max = Math.max(0.05, ...[...mape.values()].flatMap((e) => [e.base ?? 0, e.mint ?? 0]));
  const interconnections = [...new Set(regions.map((r) => r.interconnection))];
  const subregionsOf = (authority: string) => [...mape.keys()].filter((n) => n.startsWith(`${authority}.`)).sort();

  const Line = ({ node, label, depth }: { node: string; label: string; depth: number }) => {
    const e = mape.get(node);
    return (
      <li className="grid grid-cols-[minmax(0,1fr)_minmax(90px,140px)_minmax(90px,140px)] gap-x-3 items-center py-0.5 border-b border-hairline/60" style={{ paddingLeft: depth * 16 }} data-node={node}>
        <span className={`truncate ${depth <= 1 ? "font-semibold" : ""} ${depth >= 4 ? "text-ink2" : ""}`}>{label}</span>
        <Bar value={e?.base ?? null} max={max} color={METHOD_COLOR.base ?? ""} />
        <Bar value={e?.mint ?? null} max={max} color={METHOD_COLOR.mint ?? ""} />
      </li>
    );
  };

  return (
    <>
      <ChartFrame
        title="The tree: MAPE per node before and after MinT, from the lower 48 to the subregion"
        callout={treeCallout}
        provenance={treeProvenance}
        table={
          nodes.rows
            ? {
                columns: ["Node", "Level", "Base MAPE", "MinT MAPE"],
                formats: ["text", "int", "pct2", "pct2"],
                rows: [...mape.entries()].map(([node, e]) => [node, e.level, e.base, e.mint]),
              }
            : null
        }
        testId="hierarchy-tree"
        wide
      >
        {nodes.rows ? (
          <div className="text-sm">
            <div className="grid grid-cols-[minmax(0,1fr)_minmax(90px,140px)_minmax(90px,140px)] gap-x-3 text-xs text-ink2 border-b border-hairline pb-1 mb-1">
              <span>Node</span>
              <span>Base MAPE</span>
              <span>MinT MAPE</span>
            </div>
            <ul>
              <Line node="US48" label="Lower 48" depth={0} />
              {interconnections.map((ic) => (
                <li key={ic}>
                  <ul>
                    <Line node={ic} label={`${ic} interconnection`} depth={1} />
                    {regions
                      .filter((r) => r.interconnection === ic)
                      .map((r) => (
                        <li key={r.code}>
                          <details open={false}>
                            <summary className="cursor-pointer list-none">
                              <ul>
                                <Line node={r.code} label={`${r.label} (${authorities.filter((a) => a.region === r.code).length} authorities, click to open)`} depth={2} />
                              </ul>
                            </summary>
                            <ul>
                              {authorities
                                .filter((a) => a.region === r.code)
                                .map((a) => (
                                  <li key={a.authority}>
                                    <ul>
                                      <Line node={a.authority} label={a.authority} depth={3} />
                                      {subregionsOf(a.authority).map((s) => (
                                        <Line key={s} node={s} label={s.endsWith(".rest") ? `${a.authority} remainder` : s} depth={4} />
                                      ))}
                                    </ul>
                                  </li>
                                ))}
                            </ul>
                          </details>
                        </li>
                      ))}
                  </ul>
                </li>
              ))}
            </ul>
          </div>
        ) : nodes.error ? (
          <p className="p-4 text-sm text-ink2">{nodes.error}</p>
        ) : (
          <div className="skeleton h-96" />
        )}
      </ChartFrame>

      <div className="mt-5">
        <ChartFrame
          title="Accuracy by level, before and after each method"
          callout={levelsCallout}
          provenance={levelsProvenance}
          table={
            levels.rows
              ? {
                  columns: ["Method", "Level", "Nodes", "Rows", "MAPE", "lower", "upper", "90% coverage"],
                  formats: ["text", "text", "int", "int", "pct2", "pct2", "pct2", "pct1"],
                  rows: levels.rows.map((r) => [METHOD_LABEL[r.method] ?? r.method, r.level_name, r.nodes, r.rows, r.mape, r.mape_lower, r.mape_upper, r.coverage_90]),
                }
              : null
          }
          testId="hierarchy-levels"
        >
          {levels.rows ? (
            <GroupedBars
              groups={[...new Set(levels.rows.map((r) => r.level_name))].map((name) => ({
                key: name,
                label: name,
                values: Object.fromEntries(METHODS.map((mth) => [mth, levels.rows!.find((r) => r.level_name === name && r.method === mth)?.mape ?? null])),
              }))}
              series={METHODS.map((mth) => ({ key: mth, label: METHOD_LABEL[mth] ?? mth, color: METHOD_COLOR[mth] ?? "" }))}
              fmt="pct2"
              axisLabel="MAPE over the test year"
              showValues
            />
          ) : (
            <div className="skeleton h-72" />
          )}
        </ChartFrame>
      </div>
    </>
  );
}
