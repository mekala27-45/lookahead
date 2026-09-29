"""Stage: reconciliation across the hierarchy on the real grid.

Builds every node's series (aggregates, authorities, eligible subregions and the remainder
nodes), forecasts every node with the own backend over the test year, reconciles with bottom
up, top down and MinT, checks coherence to the megawatt, and publishes accuracy by level
before and after each method with intervals. Writes results/hierarchy/*.parquet and
results/manifests/hierarchy.json.
"""

from __future__ import annotations

import json
import time

import polars as pl
from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths
from lookahead_forecast.interface import QUANTILE_COLUMNS, PanelData
from lookahead_hierarchy.nodes import build_node_panel, eligible_subregions, node_table
from lookahead_hierarchy.study import LEVEL_NAMES, helped_or_hurt, run_study
from lookahead_hierarchy.summing import SummingMatrix

from lookahead_registry.stages.data import load_hierarchy, load_panel, load_windows


def run(paths: Paths, as_of: str, seed: int, *, authorities: list[str] | None = None) -> Manifest:
    started = time.time()
    panel = load_panel(paths)
    table = pl.read_csv(paths.eia / "authorities.csv")
    eligible = table.filter(pl.col("backtest_eligible"))["authority"].to_list()
    if authorities:
        eligible = [a for a in eligible if a in authorities]
    windows = load_windows(paths)
    subregions = pl.read_parquet(paths.eia / "subregions.parquet")
    hierarchy = load_hierarchy(paths)
    weather = pl.read_parquet(paths.weather / "hourly.parquet")
    subs = eligible_subregions(subregions, eligible, windows)
    nodes = node_table(hierarchy, eligible, subs)
    node_panel = build_node_panel(panel, subregions, weather, nodes, eligible)
    data = PanelData.from_frames(node_panel, None, windows, "real:eia930")
    summing = SummingMatrix.from_table(nodes)
    study = run_study(data, summing, seed)
    seconds = time.time() - started

    folder = paths.results / "hierarchy"
    folder.mkdir(parents=True, exist_ok=True)
    nodes.write_csv(folder / "nodes.csv")
    scores = pl.DataFrame(
        [
            {
                "method": s.method,
                "level": s.level,
                "level_name": LEVEL_NAMES.get(s.level, str(s.level)),
                "nodes": s.nodes,
                "rows": s.rows,
                "mape": s.mape,
                "mape_lower": s.mape_lower,
                "mape_upper": s.mape_upper,
                "coverage_90": s.coverage_90,
            }
            for s in study.scores
        ]
    )
    scores.write_parquet(folder / "scores_by_level.parquet")
    by_node = pl.DataFrame(
        [
            {"method": s.method, "level": s.level, "node": n, "mape": v}
            for s in study.scores
            for n, v in s.mape_by_node.items()
        ]
    )
    by_node.write_parquet(folder / "scores_by_node.parquet")
    # The reconciled medians for the site's tree and the authority pages: one row per node and target hour.
    median = QUANTILE_COLUMNS.index("q50")
    rows = []
    for method, q in study.reconciled.items():
        for j, node in enumerate(summing.nodes):
            rows.append(
                pl.DataFrame(
                    {
                        "method": [method] * study.rows,
                        "node": [node] * study.rows,
                        "origin": study.keys["origin"],
                        "horizon": study.keys["horizon"],
                        "target_hour": study.keys["target_hour"],
                        "q50": q[:, j, median],
                        "actual": study.actual[:, j],
                    }
                )
            )
    pl.concat(rows).write_parquet(folder / "reconciled.parquet", compression="zstd")
    (folder / "coherence.json").write_text(
        json.dumps(
            {
                "gaps_mw": study.coherence_gap_mw,
                "shrinkage_intensity": study.shrinkage_intensity,
                "rows": study.rows,
                "origins": study.origins,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = Manifest(as_of=as_of, seed=seed)
    w = Scribe(
        manifest,
        source="real:eia930",
        model="own",
        population=f"{len(summing.nodes)} nodes of the hierarchy, test year",
        origin="lookahead_registry.stages.hierarchy",
    )
    w.put("hierarchy.nodes", len(summing.nodes), "int")
    w.put("hierarchy.leaves", len(summing.leaves), "int")
    w.put("hierarchy.authorities", len(eligible), "int")
    w.put("hierarchy.subregions", subs.height, "int")
    w.put("hierarchy.authorities_with_subregions", subs["authority"].n_unique(), "int")
    w.put("hierarchy.remainder_nodes", nodes.filter(pl.col("kind") == "remainder").height, "int")
    w.put("hierarchy.rows", study.rows, "int")
    w.put("hierarchy.origins", study.origins, "int")
    w.put("hierarchy.seconds", seconds, "float1")
    w.put("hierarchy.shrinkage_intensity", study.shrinkage_intensity, "float3")
    for method, gap in study.coherence_gap_mw.items():
        w.put(f"hierarchy.coherence_gap_mw.{method}", gap, "float4" if method != "base" else "mw")
    w.put(
        "hierarchy.coherent_methods",
        ", ".join(m for m, g in study.coherence_gap_mw.items() if m != "base" and g < 1e-3) or "none",
        "text",
    )
    table_rows: list[list[Scalar]] = []
    for s in study.scores:
        table_rows.append(
            [
                s.method,
                LEVEL_NAMES.get(s.level, str(s.level)),
                s.nodes,
                s.rows,
                s.mape,
                s.mape_lower,
                s.mape_upper,
                s.coverage_90,
            ]
        )
        w.put(f"hierarchy.{s.method}.level{s.level}.mape", s.mape, "pct2")
        w.put(f"hierarchy.{s.method}.level{s.level}.mape_lower", s.mape_lower, "pct2")
        w.put(f"hierarchy.{s.method}.level{s.level}.mape_upper", s.mape_upper, "pct2")
        w.put(f"hierarchy.{s.method}.level{s.level}.coverage_90", s.coverage_90, "pct1")
    w.table(
        "hierarchy.by_level",
        ["Method", "Level", "Nodes", "Rows", "MAPE", "lower", "upper", "90 pct coverage"],
        ["text", "text", "int", "int", "pct2", "pct2", "pct2", "pct1"],
        table_rows,
    )
    verdicts = helped_or_hurt(study.scores)
    w.table(
        "hierarchy.helped_or_hurt",
        ["Method", "Level", "Base MAPE", "Reconciled MAPE", "Change", "Verdict"],
        ["text", "text", "pct2", "pct2", "spct1", "text"],
        [
            [
                str(v["method"]),
                str(v["level_name"]),
                float(str(v["base_mape"])),
                float(str(v["mape"])),
                float(str(v["change"])),
                str(v["verdict"]),
            ]
            for v in verdicts
        ],
    )
    for v in verdicts:
        w.put(f"hierarchy.verdict.{v['method']}.level{v['level']}", str(v["verdict"]), "text")
    best_method = min(
        ("bottom_up", "top_down", "mint"), key=lambda m: sum(s.mape for s in study.scores if s.method == m)
    )
    w.put("hierarchy.best_method", best_method, "text")
    hurt = [f"{v['method']} at the {v['level_name']} level" for v in verdicts if v["verdict"] == "hurt"]
    w.put("hierarchy.hurt_list", "; ".join(hurt) or "none", "text")
    helped = [f"{v['method']} at the {v['level_name']} level" for v in verdicts if v["verdict"] == "helped"]
    w.put("hierarchy.helped_list", "; ".join(helped) or "none", "text")
    manifest.save(paths.results / "manifests" / "hierarchy.json")
    return manifest
