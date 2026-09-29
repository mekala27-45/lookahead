"""Summaries of a scoring frame: the tables the pages and the memo print, every one with intervals.

Everything here is a ratio of day sums bootstrapped in blocks (see bootstrap.py), so a
table cell's interval means the same thing wherever it appears.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl
from lookahead_core.config import QUANTILE_LEVELS
from lookahead_core.frames import as_float
from lookahead_forecast.interface import QUANTILE_COLUMNS

from lookahead_evaluation.bootstrap import bootstrap_statistic
from lookahead_evaluation.metrics import (
    PEAK_SUM_COLUMNS,
    daily_peaks,
    day_sums,
    peak_day_sums,
    peak_ratio,
    reliability,
    row_errors,
    stat_coverage_50,
    stat_coverage_90,
    stat_crps,
    stat_mape,
    stat_mape_naive,
    stat_mape_operator,
    stat_mase,
    stat_pinball,
    sums_matrix,
)


@dataclass
class Stat:
    value: float
    lower: float
    upper: float


@dataclass
class Summary:
    overall: dict[str, Stat] = field(default_factory=dict)
    by_authority: list[dict[str, float | str]] = field(default_factory=list)
    by_horizon: list[dict[str, float]] = field(default_factory=list)
    by_local_hour: list[dict[str, float]] = field(default_factory=list)
    reliability: list[tuple[float, float, int]] = field(default_factory=list)
    peaks: dict[str, Stat] = field(default_factory=dict)
    peaks_by_authority: list[dict[str, float | str]] = field(default_factory=list)
    interior: list[dict[str, float | str]] = field(default_factory=list)
    degenerate_levels: list[str] = field(default_factory=list)
    rows_scored: int = 0
    rows_unscored: int = 0


def _pooled_by_day(day_frame: pl.DataFrame) -> np.ndarray:
    """Sum every authority's day sums per day so the bootstrap resamples days jointly."""
    pooled = (
        day_frame.group_by("origin_day")
        .agg([pl.col(c).sum() for c in day_frame.columns if c not in ("authority", "origin_day")])
        .sort("origin_day")
    )
    return sums_matrix(pooled)


STATS = {
    "mape": stat_mape,
    "mape_operator": stat_mape_operator,
    "mape_naive": stat_mape_naive,
    "mase": stat_mase,
    "crps": stat_crps,
    "coverage_50": stat_coverage_50,
    "coverage_90": stat_coverage_90,
}


def summarise(scoring: pl.DataFrame, seed: int, label: str, with_intervals: bool = True) -> Summary:
    out = Summary()
    errors = row_errors(scoring)
    out.rows_scored = errors.height
    out.rows_unscored = scoring.height - errors.height
    if errors.height == 0:
        return out
    days = day_sums(errors)
    pooled = _pooled_by_day(days)

    def stat(sums: np.ndarray, fn: object, *stream: str) -> Stat:
        if with_intervals:
            value, lower, upper, _ = bootstrap_statistic(sums, fn, seed, label, *stream)  # type: ignore[arg-type]
            return Stat(value, lower, upper)
        value = float(fn(sums.sum(axis=0, keepdims=True))[0])  # type: ignore[operator]
        return Stat(value, value, value)

    for name, fn in STATS.items():
        out.overall[name] = stat(pooled, fn, "overall", name)
    for c in QUANTILE_COLUMNS:
        out.overall[f"pinball_{c}"] = stat(pooled, stat_pinball(c), "overall", c)

    for authority in sorted(errors["authority"].unique().to_list()):
        sums = sums_matrix(days.filter(pl.col("authority") == authority))
        row: dict[str, float | str] = {"authority": authority, "hours": float(sums[:, 0].sum())}
        for name, fn in STATS.items():
            s = stat(sums, fn, "authority", authority, name)
            row[name] = s.value
            row[f"{name}_lower"] = s.lower
            row[f"{name}_upper"] = s.upper
        out.by_authority.append(row)

    by_h = day_sums(errors, ["horizon"])
    for h in sorted(by_h["horizon"].unique().to_list()):
        sums = _pooled_by_day(by_h.filter(pl.col("horizon") == h).drop("horizon"))
        totals = sums.sum(axis=0, keepdims=True)
        out.by_horizon.append(
            {
                "horizon": float(h),
                "mape": float(stat_mape(totals)[0]),
                "mape_operator": float(stat_mape_operator(totals)[0]),
                "mape_naive": float(stat_mape_naive(totals)[0]),
                "coverage_90": float(stat_coverage_90(totals)[0]),
                "coverage_50": float(stat_coverage_50(totals)[0]),
                "crps": float(stat_crps(totals)[0]),
            }
        )
    by_hour = day_sums(errors, ["local_hour"])
    for hour in sorted(by_hour["local_hour"].unique().to_list()):
        sums = _pooled_by_day(by_hour.filter(pl.col("local_hour") == hour).drop("local_hour"))
        totals = sums.sum(axis=0, keepdims=True)
        out.by_local_hour.append(
            {
                "local_hour": float(hour),
                "mape": float(stat_mape(totals)[0]),
                "mape_operator": float(stat_mape_operator(totals)[0]),
                "mape_naive": float(stat_mape_naive(totals)[0]),
                "coverage_90": float(stat_coverage_90(totals)[0]),
            }
        )
    out.reliability = reliability(errors)

    peaks = daily_peaks(scoring)
    if peaks.height:
        pk = peak_day_sums(peaks)
        pooled_pk = (
            pk.group_by("origin_day")
            .agg([pl.col(c).sum() for c in PEAK_SUM_COLUMNS])
            .sort("origin_day")
            .select(list(PEAK_SUM_COLUMNS))
            .to_numpy()
            .astype(np.float64)
        )
        for name in PEAK_SUM_COLUMNS[1:-1]:
            out.peaks[name] = stat(pooled_pk, peak_ratio(name), "peaks", name)
        out.peaks["model_timing_median"] = Stat(
            as_float(peaks["model_timing_error"].abs().median()), float("nan"), float("nan")
        )
        out.peaks["operator_timing_median"] = Stat(
            as_float(peaks.filter(pl.col("operator_missing") == 0)["operator_timing_error"].abs().median()),
            float("nan"),
            float("nan"),
        )
        for authority in sorted(peaks["authority"].unique().to_list()):
            sums = (
                pk.filter(pl.col("authority") == authority)
                .select(list(PEAK_SUM_COLUMNS))
                .to_numpy()
                .astype(np.float64)
            )
            totals = sums.sum(axis=0, keepdims=True)
            row_p: dict[str, float | str] = {"authority": authority, "days": float(totals[0, 0])}
            for name in PEAK_SUM_COLUMNS[1:-1]:
                row_p[name] = float(peak_ratio(name)(totals)[0])  # type: ignore[operator]
            sub = peaks.filter(pl.col("authority") == authority)
            row_p["model_timing_median"] = as_float(sub["model_timing_error"].abs().median())
            out.peaks_by_authority.append(row_p)

    # The interior test on the served levels: an empirical coverage of zero or one is degenerate.
    for q, c in zip(QUANTILE_LEVELS, QUANTILE_COLUMNS, strict=True):
        below = as_float((errors["actual"] <= errors[c]).mean())
        degenerate = below <= 0.0 or below >= 1.0
        out.interior.append({"level": q, "share_below": below, "interior": "no" if degenerate else "yes"})
        if degenerate:
            out.degenerate_levels.append(c)
    return out
