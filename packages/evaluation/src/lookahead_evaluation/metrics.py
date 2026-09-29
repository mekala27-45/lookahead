"""The metrics an operator uses, on the scoring frame.

Point: MAPE, MASE against the weekly seasonal naive. Probabilistic: pinball loss at each
level, CRPS as the integral of the pinball loss over the served levels, coverage of the 50
and 90 percent intervals. Daily: the peak error, the peak timing error, the morning and
evening ramp errors, each over the target day (the first full local day after the origin).
Every aggregate is a ratio of sums so the block bootstrap can resample days.
"""

from __future__ import annotations

import numpy as np
import polars as pl
from lookahead_core.config import QUANTILE_LEVELS
from lookahead_core.frames import as_float
from lookahead_forecast.interface import QUANTILE_COLUMNS

MORNING_RAMP = (5, 9)
"""Local hours: the rise from the hour beginning 05:00 to the hour beginning 09:00."""
EVENING_RAMP = (15, 19)

DAY_SUM_COLUMNS = (
    "n",
    "ape_model",
    "ape_operator",
    "ape_naive",
    "ae_model",
    "ae_operator",
    "ae_naive",
    "in50",
    "in90",
    "crps",
    *[f"pinball_{c}" for c in QUANTILE_COLUMNS],
    "n_operator",
    "ape_model_paired",
    "ape_operator_paired",
)


def scoreable(scoring: pl.DataFrame) -> pl.DataFrame:
    """Rows with a positive actual and a finite median forecast."""
    return scoring.filter(
        pl.col("actual").is_not_null()
        & pl.col("actual").is_not_nan()
        & (pl.col("actual") > 0)
        & pl.col("q50").is_not_null()
        & pl.col("q50").is_not_nan()
    )


def row_errors(scoring: pl.DataFrame) -> pl.DataFrame:
    """Per row errors for the backend's quantiles, the operator and the naive."""
    s = scoreable(scoring)
    exprs: list[pl.Expr] = [
        ((pl.col("q50") - pl.col("actual")).abs() / pl.col("actual")).alias("ape_model"),
        ((pl.col("operator") - pl.col("actual")).abs() / pl.col("actual")).alias("ape_operator"),
        ((pl.col("naive") - pl.col("actual")).abs() / pl.col("actual")).alias("ape_naive"),
        (pl.col("q50") - pl.col("actual")).abs().alias("ae_model"),
        (pl.col("operator") - pl.col("actual")).abs().alias("ae_operator"),
        (pl.col("naive") - pl.col("actual")).abs().alias("ae_naive"),
        ((pl.col("actual") >= pl.col("q25")) & (pl.col("actual") <= pl.col("q75")))
        .cast(pl.Float64)
        .alias("in50"),
        ((pl.col("actual") >= pl.col("q05")) & (pl.col("actual") <= pl.col("q95")))
        .cast(pl.Float64)
        .alias("in90"),
        pl.col("operator")
        .is_not_null()
        .and_(pl.col("operator").is_not_nan())
        .cast(pl.Float64)
        .alias("has_operator"),
    ]
    for q, c in zip(QUANTILE_LEVELS, QUANTILE_COLUMNS, strict=True):
        diff = pl.col("actual") - pl.col(c)
        exprs.append(pl.when(diff >= 0).then(q * diff).otherwise((q - 1) * diff).alias(f"pinball_{c}"))
    s = s.with_columns(exprs)
    # CRPS as the trapezoid integral of twice the pinball loss over the served levels, relative to the actual.
    levels = np.asarray(QUANTILE_LEVELS)
    weights = np.zeros(len(levels))
    for i in range(len(levels) - 1):
        w = levels[i + 1] - levels[i]
        weights[i] += w / 2
        weights[i + 1] += w / 2
    crps = sum(2.0 * float(weights[i]) * pl.col(f"pinball_{c}") for i, c in enumerate(QUANTILE_COLUMNS))
    return s.with_columns((crps / pl.col("actual")).alias("crps"))


def day_sums(errors: pl.DataFrame, extra_keys: list[str] | None = None) -> pl.DataFrame:
    """Sums per (authority, origin_day, extra keys) for the bootstrap."""
    keys = ["authority", "origin_day", *(extra_keys or [])]
    paired = pl.col("has_operator") == 1.0
    aggs = [
        pl.len().cast(pl.Float64).alias("n"),
        pl.col("ape_model").sum().alias("ape_model"),
        pl.col("ape_operator").filter(paired).sum().alias("ape_operator"),
        pl.col("ape_naive").sum().alias("ape_naive"),
        pl.col("ae_model").sum().alias("ae_model"),
        pl.col("ae_operator").filter(paired).sum().alias("ae_operator"),
        pl.col("ae_naive").sum().alias("ae_naive"),
        pl.col("in50").sum().alias("in50"),
        pl.col("in90").sum().alias("in90"),
        pl.col("crps").sum().alias("crps"),
        *[pl.col(f"pinball_{c}").sum().alias(f"pinball_{c}") for c in QUANTILE_COLUMNS],
        pl.col("has_operator").sum().alias("n_operator"),
        pl.col("ape_model").filter(paired).sum().alias("ape_model_paired"),
        pl.col("ape_operator").filter(paired).sum().alias("ape_operator_paired"),
    ]
    return errors.group_by(keys).agg(aggs).sort(keys).fill_null(0.0)


def sums_matrix(day_frame: pl.DataFrame) -> np.ndarray:
    return day_frame.select(list(DAY_SUM_COLUMNS)).to_numpy().astype(np.float64)


def column(name: str) -> int:
    return DAY_SUM_COLUMNS.index(name)


def stat_mape(totals: np.ndarray) -> np.ndarray:
    out: np.ndarray = totals[:, column("ape_model")] / totals[:, column("n")]
    return out


def stat_mape_operator(totals: np.ndarray) -> np.ndarray:
    out: np.ndarray = totals[:, column("ape_operator_paired")] / totals[:, column("n_operator")]
    return out


def stat_mape_naive(totals: np.ndarray) -> np.ndarray:
    out: np.ndarray = totals[:, column("ape_naive")] / totals[:, column("n")]
    return out


def stat_mase(totals: np.ndarray) -> np.ndarray:
    out: np.ndarray = totals[:, column("ae_model")] / totals[:, column("ae_naive")]
    return out


def stat_coverage_50(totals: np.ndarray) -> np.ndarray:
    out: np.ndarray = totals[:, column("in50")] / totals[:, column("n")]
    return out


def stat_coverage_90(totals: np.ndarray) -> np.ndarray:
    out: np.ndarray = totals[:, column("in90")] / totals[:, column("n")]
    return out


def stat_crps(totals: np.ndarray) -> np.ndarray:
    out: np.ndarray = totals[:, column("crps")] / totals[:, column("n")]
    return out


def stat_pinball(level_column: str) -> object:
    idx = column(f"pinball_{level_column}")

    def inner(totals: np.ndarray) -> np.ndarray:
        out: np.ndarray = totals[:, idx] / totals[:, column("n")]
        return out

    return inner


def stat_skill(totals: np.ndarray) -> np.ndarray:
    """One minus the model's MAPE over the operator's, on the rows where both exist."""
    model = totals[:, column("ape_model_paired")] / totals[:, column("n_operator")]
    operator = totals[:, column("ape_operator_paired")] / totals[:, column("n_operator")]
    with np.errstate(invalid="ignore", divide="ignore"):
        skill: np.ndarray = 1.0 - model / operator
    return skill


def daily_peaks(scoring: pl.DataFrame) -> pl.DataFrame:
    """Per authority and origin: the target day's peak and its timing for the model, the operator and the actual."""
    s = scoreable(scoring).filter(
        pl.col("target_day").is_not_null() & (pl.col("local_day") == pl.col("target_day"))
    )
    s = s.with_columns(pl.col("operator").fill_nan(None), pl.col("naive").fill_nan(None))
    by = ["authority", "origin", "origin_day", "target_day"]
    out = s.group_by(by).agg(
        pl.len().alias("hours"),
        pl.col("actual").max().alias("actual_peak"),
        pl.col("q50").max().alias("model_peak"),
        pl.col("operator").max().alias("operator_peak"),
        pl.col("naive").max().alias("naive_peak"),
        pl.col("local_hour").sort_by("actual", descending=True).first().alias("actual_peak_hour"),
        pl.col("local_hour").sort_by("q50", descending=True).first().alias("model_peak_hour"),
        pl.col("local_hour")
        .sort_by("operator", descending=True, nulls_last=True)
        .first()
        .alias("operator_peak_hour"),
        pl.col("operator").null_count().alias("operator_missing"),
        _ramp_expr("actual", MORNING_RAMP).alias("actual_morning_ramp"),
        _ramp_expr("q50", MORNING_RAMP).alias("model_morning_ramp"),
        _ramp_expr("operator", MORNING_RAMP).alias("operator_morning_ramp"),
        _ramp_expr("actual", EVENING_RAMP).alias("actual_evening_ramp"),
        _ramp_expr("q50", EVENING_RAMP).alias("model_evening_ramp"),
        _ramp_expr("operator", EVENING_RAMP).alias("operator_evening_ramp"),
    )
    out = out.filter(pl.col("hours") == 24)
    return out.with_columns(
        ((pl.col("model_peak") - pl.col("actual_peak")) / pl.col("actual_peak")).alias("model_peak_error"),
        ((pl.col("operator_peak") - pl.col("actual_peak")) / pl.col("actual_peak")).alias(
            "operator_peak_error"
        ),
        ((pl.col("naive_peak") - pl.col("actual_peak")) / pl.col("actual_peak")).alias("naive_peak_error"),
        (pl.col("model_peak_hour") - pl.col("actual_peak_hour")).alias("model_timing_error"),
        (pl.col("operator_peak_hour") - pl.col("actual_peak_hour")).alias("operator_timing_error"),
        ((pl.col("model_morning_ramp") - pl.col("actual_morning_ramp")) / pl.col("actual_peak")).alias(
            "model_morning_ramp_error"
        ),
        ((pl.col("operator_morning_ramp") - pl.col("actual_morning_ramp")) / pl.col("actual_peak")).alias(
            "operator_morning_ramp_error"
        ),
        ((pl.col("model_evening_ramp") - pl.col("actual_evening_ramp")) / pl.col("actual_peak")).alias(
            "model_evening_ramp_error"
        ),
        ((pl.col("operator_evening_ramp") - pl.col("actual_evening_ramp")) / pl.col("actual_peak")).alias(
            "operator_evening_ramp_error"
        ),
    ).sort(["authority", "origin"])


def _ramp_expr(value: str, window: tuple[int, int]) -> pl.Expr:
    start, end = window
    at_end = pl.col(value).filter(pl.col("local_hour") == end).first()
    at_start = pl.col(value).filter(pl.col("local_hour") == start).first()
    return at_end - at_start


def peak_day_sums(peaks: pl.DataFrame) -> pl.DataFrame:
    """Per (authority, origin_day) sums for the peak metrics, absolute errors and counts."""
    return (
        peaks.group_by(["authority", "origin_day"])
        .agg(
            pl.len().cast(pl.Float64).alias("days"),
            pl.col("model_peak_error").abs().sum().alias("model_peak_abs"),
            pl.col("operator_peak_error").abs().sum().alias("operator_peak_abs"),
            pl.col("naive_peak_error").abs().sum().alias("naive_peak_abs"),
            pl.col("model_timing_error").abs().sum().alias("model_timing_abs"),
            pl.col("operator_timing_error").abs().sum().alias("operator_timing_abs"),
            pl.col("model_morning_ramp_error").abs().sum().alias("model_morning_abs"),
            pl.col("operator_morning_ramp_error").abs().sum().alias("operator_morning_abs"),
            pl.col("model_evening_ramp_error").abs().sum().alias("model_evening_abs"),
            pl.col("operator_evening_ramp_error").abs().sum().alias("operator_evening_abs"),
            (pl.col("operator_missing") == 0).cast(pl.Float64).sum().alias("days_with_operator"),
        )
        .sort(["authority", "origin_day"])
        .fill_null(0.0)
    )


PEAK_SUM_COLUMNS = (
    "days",
    "model_peak_abs",
    "operator_peak_abs",
    "naive_peak_abs",
    "model_timing_abs",
    "operator_timing_abs",
    "model_morning_abs",
    "operator_morning_abs",
    "model_evening_abs",
    "operator_evening_abs",
    "days_with_operator",
)


def peak_ratio(numerator: str) -> object:
    i = PEAK_SUM_COLUMNS.index(numerator)
    d = (
        PEAK_SUM_COLUMNS.index("days_with_operator")
        if numerator.startswith("operator")
        else PEAK_SUM_COLUMNS.index("days")
    )

    def inner(totals: np.ndarray) -> np.ndarray:
        with np.errstate(invalid="ignore", divide="ignore"):
            out: np.ndarray = totals[:, i] / totals[:, d]
        return out

    return inner


def reliability(errors: pl.DataFrame) -> list[tuple[float, float, int]]:
    """For each served level, the share of actuals at or below the quantile: the reliability diagram."""
    out = []
    for q, c in zip(QUANTILE_LEVELS, QUANTILE_COLUMNS, strict=True):
        share = as_float((errors["actual"] <= errors[c]).mean())
        out.append((q, share, errors.height))
    return out
