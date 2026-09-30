"""The second hierarchy: the panel total over its load shape clusters, forecast by the gbm backend
and reconciled with MinT.

Each cluster's hourly load over a fixed panel of households (those reporting through the whole
window, so the series measures consumption rather than recruitment) and the panel total are
forecast directly by the global gbm backend at daily origins over the last three months of the
release, with the year before as validation. The MinT covariance is the shrunk covariance of
the calibration model's validation residuals; the reconciled total and clusters are scored
against the actuals with block bootstrap intervals over test days, before and after.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import polars as pl
from lookahead_core.config import POLICY
from lookahead_evaluation.bootstrap import bootstrap_statistic
from lookahead_evaluation.harness import run_backend
from lookahead_evaluation.metrics import day_sums, row_errors, stat_coverage_90, stat_mape, sums_matrix
from lookahead_forecast.gbm import GbmForecaster, _predict
from lookahead_forecast.interface import QUANTILE_COLUMNS, ForecastSpec, PanelData
from lookahead_hierarchy.reconcile import reconcile_quantiles, shrink_covariance
from lookahead_hierarchy.study import _aligned
from lookahead_hierarchy.summing import SummingMatrix, check_coherent

TOTAL = "PANEL"


def cluster_panel(loads: pl.DataFrame, tz_offset_hours: int = 0) -> pl.DataFrame:
    """The hourly cluster loads plus the total as a panel in the grid's schema: authority is the
    node, demand is kWh, no operator forecast, no weather (stated on the page)."""
    if loads.height == 0:
        raise ValueError("no cluster loads")
    clusters = loads.with_columns(pl.col("cluster").cast(pl.Utf8).alias("authority"))
    total = (
        loads.group_by("ts")
        .agg(pl.col("kwh").sum().alias("kwh"), pl.col("households").sum().alias("households"))
        .with_columns(pl.lit(TOTAL).alias("authority"))
    )
    frame = pl.concat(
        [
            clusters.select("authority", "ts", "kwh", "households"),
            total.select("authority", "ts", "kwh", "households"),
        ]
    )
    return (
        frame.rename({"ts": "utc_hour", "kwh": "demand"})
        .with_columns(
            pl.col("utc_hour").dt.replace_time_zone("UTC"),
            pl.col("demand").cast(pl.Float64),
            pl.lit(None, dtype=pl.Float64).alias("forecast_operator"),
            pl.lit(tz_offset_hours, dtype=pl.Int64).alias("utc_offset_hours"),
            pl.lit("London").alias("region"),
        )
        .sort(["authority", "utc_hour"])
    )


def meter_windows(last_hour: datetime, test_days: int = POLICY.meter_test_days) -> dict[str, str | int]:
    test_end = last_hour.replace(hour=0, minute=0, second=0, microsecond=0)
    test_start = test_end - timedelta(days=test_days - 1)
    validation_start = test_start - timedelta(days=365)
    return {
        "training_start": (validation_start - timedelta(days=91)).date().isoformat(),
        "validation_start": validation_start.date().isoformat(),
        "test_start": test_start.date().isoformat(),
        "test_end": test_end.date().isoformat(),
    }


def summing_for(clusters: list[str]) -> SummingMatrix:
    table = pl.DataFrame(
        {
            "node": [TOTAL, *clusters],
            "parent": [None, *[TOTAL] * len(clusters)],
            "level": [0, *[1] * len(clusters)],
            "kind": ["panel", *["cluster"] * len(clusters)],
            "label": ["panel total", *[f"cluster {c}" for c in clusters]],
        }
    )
    return SummingMatrix.from_table(table)


@dataclass
class MeterForecast:
    scores: pl.DataFrame
    """method, level, mape, lower, upper, coverage_90, rows."""
    coherence_gap: dict[str, float]
    shrinkage_intensity: float
    origins: int
    fits: int
    rows: int
    base_scoring: pl.DataFrame
    reconciled_total: pl.DataFrame
    """origin, horizon, target_hour, base q50, mint q50, actual for the panel total."""
    windows: dict[str, str | int]


def _validation_residuals(fitted: Any, data: PanelData, nodes: list[str]) -> np.ndarray:
    """Residuals of the calibration model over the validation origins, aligned across nodes."""
    boosters = fitted.boosters["calibration"]
    frames = []
    for node in nodes:
        d = fitted.designs[node]
        a = data.authorities[node]
        valid = (
            (d.origin_position >= a.series.position(data.validation_start))
            & (d.origin_position < a.series.position(data.test_start))
            & d.usable
        )
        q = _predict(boosters, d.x[valid])
        median = q[:, QUANTILE_COLUMNS.index("q50")]
        frames.append(
            pl.DataFrame(
                {
                    "origin_position": d.origin_position[valid],
                    "horizon": d.horizon[valid],
                    node: (d.y_ratio[valid] - median) * d.scale[valid],
                }
            )
        )
    aligned = frames[0]
    for f in frames[1:]:
        aligned = aligned.join(f, on=["origin_position", "horizon"], how="inner")
    return aligned.select(nodes).to_numpy().astype(np.float64)


def _score(
    quantiles: np.ndarray, actual: np.ndarray, keys: pl.DataFrame, nodes: list[str], seed: int, method: str
) -> list[dict[str, Any]]:
    out = []
    origin_day = keys.select((pl.col("origin") - pl.duration(hours=1)).dt.date().alias("day"))[
        "day"
    ].to_list()
    for level, members in ((0, [TOTAL]), (1, [n for n in nodes if n != TOTAL])):
        rows = []
        for node in members:
            j = nodes.index(node)
            frame = pl.DataFrame(
                {
                    "authority": [node] * len(origin_day),
                    "origin_day": origin_day,
                    "horizon": keys["horizon"].to_list(),
                    "actual": actual[:, j],
                    **{c: quantiles[:, j, k] for k, c in enumerate(QUANTILE_COLUMNS)},
                    "operator": [float("nan")] * len(origin_day),
                    "naive": [float("nan")] * len(origin_day),
                }
            )
            rows.append(frame)
        scoring = pl.concat(rows)
        errors = row_errors(scoring)
        sums = sums_matrix(day_sums(errors))
        mape, lower, upper, _ = bootstrap_statistic(sums, stat_mape, seed, "meter", method, level)
        coverage = float(stat_coverage_90(sums.sum(axis=0, keepdims=True))[0])
        out.append(
            {
                "method": method,
                "level": level,
                "level_name": "panel total" if level == 0 else "clusters",
                "mape": mape,
                "lower": lower,
                "upper": upper,
                "coverage_90": coverage,
                "rows": int(errors.height),
            }
        )
    return out


def forecast_and_reconcile(panel: pl.DataFrame, windows: dict[str, str | int], seed: int) -> MeterForecast:
    data = PanelData.from_frames(panel, None, windows, "real:lcl")
    nodes = [TOTAL, *[n for n in data.names if n != TOTAL]]
    summing = summing_for([n for n in nodes if n != TOTAL])
    spec = ForecastSpec(backend="gbm", seed=seed)
    result = run_backend(data, GbmForecaster(), spec)
    keys, base, actual = _aligned(result.scoring, summing.nodes)
    finite = np.all(np.isfinite(base), axis=(1, 2)) & np.all(np.isfinite(actual), axis=1)
    keys, base, actual = keys.filter(pl.Series(finite)), base[finite], actual[finite]
    if base.shape[0] == 0:
        raise ValueError("no test row has a base forecast for every node")
    residuals = _validation_residuals(result.fitted, data, summing.nodes)
    covariance, intensity = shrink_covariance(residuals)
    reconciled = {
        "base": base,
        "bottom_up": reconcile_quantiles(base, summing, "bottom_up"),
        "mint": reconcile_quantiles(base, summing, "mint", covariance=covariance),
    }
    median = QUANTILE_COLUMNS.index("q50")
    gaps = {m: check_coherent(reconciled[m][:, :, median], summing) for m in ("bottom_up", "mint")}
    try:
        gaps["base"] = check_coherent(base[:, :, median], summing)
    except Exception:
        rebuilt = summing.aggregate(base[:, summing.leaf_index, median])
        gaps["base"] = float(np.nanmax(np.abs(rebuilt - base[:, :, median])))
    scores = []
    for method, q in reconciled.items():
        scores.extend(_score(q, actual, keys, summing.nodes, seed, method))
    total_index = summing.nodes.index(TOTAL)
    reconciled_total = keys.with_columns(
        pl.Series("base_q50", base[:, total_index, median]),
        pl.Series("base_q05", base[:, total_index, QUANTILE_COLUMNS.index("q05")]),
        pl.Series("base_q95", base[:, total_index, QUANTILE_COLUMNS.index("q95")]),
        pl.Series("mint_q50", reconciled["mint"][:, total_index, median]),
        pl.Series("bottom_up_q50", reconciled["bottom_up"][:, total_index, median]),
        pl.Series("actual", actual[:, total_index]),
    )
    return MeterForecast(
        scores=pl.DataFrame(scores),
        coherence_gap=gaps,
        shrinkage_intensity=intensity,
        origins=int(result.predictions.origins),
        fits=int(result.predictions.fits),
        rows=int(base.shape[0]),
        base_scoring=result.scoring,
        reconciled_total=reconciled_total,
        windows=windows,
    )
