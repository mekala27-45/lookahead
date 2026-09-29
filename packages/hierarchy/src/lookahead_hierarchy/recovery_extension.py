"""The reconciliation graded on the simulator inside the recovery study.

Registered into the evaluation package's extension table on import, so a recovery run
reports, per condition and seed, each method's coherence gap and its accuracy against the
truth at every level, beside the harness and backend figures.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
from lookahead_evaluation import recovery
from lookahead_forecast.interface import QUANTILE_COLUMNS, PanelData

from lookahead_hierarchy.nodes import build_node_panel, eligible_subregions, node_table
from lookahead_hierarchy.study import run_study
from lookahead_hierarchy.summing import SummingMatrix


def reconciliation_on_sim(
    data: PanelData,
    panel: pl.DataFrame,
    subregions: pl.DataFrame,
    hierarchy: pl.DataFrame,
    extras: dict[str, Any],
    seed: int,
) -> dict[str, float]:
    authorities = sorted(panel["authority"].unique().to_list())
    subs = eligible_subregions(subregions, authorities, recovery.SIM_WINDOWS)
    nodes = node_table(hierarchy, authorities, subs)
    node_panel = build_node_panel(panel, subregions, None, nodes, authorities)
    node_data = PanelData.from_frames(node_panel, None, recovery.SIM_WINDOWS, "simulated")
    summing = SummingMatrix.from_table(nodes)
    study = run_study(node_data, summing, seed)
    out: dict[str, float] = {}
    for method, gap in study.coherence_gap_mw.items():
        out[f"coherence_gap_mw.{method}"] = gap
    # Accuracy against the truth, not the observed actuals: the truth panel has no defects.
    truth = extras["truth"]
    median = QUANTILE_COLUMNS.index("q50")
    true_leaf = {}
    for node in summing.leaves:
        if "." in node and not node.endswith(".rest"):
            authority, sub = node.split(".", 1)
            series = subregions.filter(
                (pl.col("authority") == authority) & (pl.col("subregion") == sub)
            ).sort("utc_hour")
            true_leaf[node] = dict(
                zip(
                    series["utc_hour"].to_list(),
                    series["demand"].cast(pl.Float64).fill_null(float("nan")).to_list(),
                    strict=True,
                )
            )
        elif node.endswith(".rest"):
            authority = node[: -len(".rest")]
            series = panel.filter(pl.col("authority") == authority).sort("utc_hour")
            parts = (
                subregions.filter(pl.col("authority") == authority)
                .group_by("utc_hour")
                .agg(pl.col("demand").sum().alias("s"))
                .sort("utc_hour")
            )
            joined = series.select("utc_hour", "demand_true").join(parts, on="utc_hour", how="inner")
            true_leaf[node] = dict(
                zip(
                    joined["utc_hour"].to_list(),
                    (joined["demand_true"] - joined["s"]).cast(pl.Float64).fill_null(float("nan")).to_list(),
                    strict=True,
                )
            )
        else:
            series = panel.filter(pl.col("authority") == node).sort("utc_hour")
            true_leaf[node] = dict(
                zip(
                    series["utc_hour"].to_list(),
                    series["demand_true"].cast(pl.Float64).fill_null(float("nan")).to_list(),
                    strict=True,
                )
            )
    hours = study.keys["target_hour"].to_list()
    leaf_truth = np.array([[true_leaf[node].get(h, np.nan) for node in summing.leaves] for h in hours])
    all_truth = summing.aggregate(leaf_truth)
    for method, q in study.reconciled.items():
        pred = q[:, :, median]
        for level in sorted(set(summing.levels.values())):
            cols = [summing.nodes.index(n) for n in summing.nodes_at(level)]
            t = all_truth[:, cols]
            p = pred[:, cols]
            ok = np.isfinite(t) & (t > 0) & np.isfinite(p)
            out[f"mape_vs_truth.{method}.level{level}"] = float(np.mean(np.abs(p[ok] - t[ok]) / t[ok]))
    base_top = out["mape_vs_truth.base.level0"]
    out["mint_gain_top"] = base_top - out["mape_vs_truth.mint.level0"]
    out["mint_gain_leaves"] = out["mape_vs_truth.base.level4"] - out["mape_vs_truth.mint.level4"]
    out["shrinkage_intensity"] = study.shrinkage_intensity
    _ = truth
    return out


def register() -> None:
    recovery.EXTENSIONS.setdefault("reconciliation", reconciliation_on_sim)
