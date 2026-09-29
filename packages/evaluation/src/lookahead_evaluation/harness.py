"""The rolling origin harness: run a backend over every test origin and build the scoring frame.

One origin per day per authority at the issue hour, horizons 1 to 48, the backend fitted
through the validation year first (thresholds, penalties, conformal offsets chosen there)
and then run day by day over the test year. The scoring frame joins each forecast row with
the actual demand at the target hour, the operator's published forecast for that hour, the
seasonal naive point and the local calendar, so every metric in packages/evaluation reads
one frame. Rows without an actual are kept and reported as unscored, never dropped in silence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import polars as pl
from lookahead_features.build import calendar_at
from lookahead_forecast.baselines import naive_point, operator_at
from lookahead_forecast.interface import Forecaster, ForecastSpec, PanelData, Predictions, Request

SCORING_COLUMNS = (
    "authority",
    "origin",
    "horizon",
    "target_hour",
    "actual",
    "operator",
    "naive",
    "local_hour",
    "local_day",
    "target_day",
    "origin_day",
)


@dataclass(frozen=True)
class RunResult:
    predictions: Predictions
    scoring: pl.DataFrame
    fit_seconds: float
    predict_seconds: float
    fitted: Any = None


def requests_for_test_period(data: PanelData) -> list[Request]:
    requests = []
    for authority in data.names:
        origins = data.origins(data.test_start, data.test_end, authority)
        a = data.authorities[authority]
        # An origin needs its 48 target hours inside the series to be scored; later ones are issued
        # by the live API, not by the backtest.
        origins = origins[origins + 48 < len(a.series.values)]
        if len(origins):
            requests.append(Request(authority=authority, origin_positions=origins))
    return requests


def run_backend(data: PanelData, forecaster: Forecaster, spec: ForecastSpec) -> RunResult:
    import time

    started = time.time()
    fitted = forecaster.fit(data, spec, data.test_start)
    fit_seconds = time.time() - started
    started = time.time()
    predictions = forecaster.predict(fitted, data, spec, requests_for_test_period(data))
    predict_seconds = time.time() - started
    return RunResult(
        predictions=predictions,
        scoring=scoring_frame(data, predictions.frame),
        fit_seconds=fit_seconds,
        predict_seconds=predict_seconds,
        fitted=fitted,
    )


def scoring_frame(data: PanelData, predictions: pl.DataFrame) -> pl.DataFrame:
    """Attach the actual, the operator, the naive point and the local calendar to every prediction row."""
    frames = []
    for authority in sorted(predictions["authority"].unique().to_list()):
        rows = predictions.filter(pl.col("authority") == authority).sort(["origin", "horizon"])
        a = data.authorities[authority]
        origins = np.asarray([a.series.position(o) for o in rows["origin"].to_list()], dtype=np.int64)
        horizon = rows["horizon"].to_numpy().astype(np.int64)
        target = origins + horizon
        n = len(a.series.values)
        actual = np.full(len(target), np.nan)
        inside = target < n
        actual[inside] = a.series.values[target[inside]]
        operator = operator_at(a, target)
        naive = naive_point(a, origins, horizon)
        offsets = a.offsets[np.clip(target, 0, n - 1)]
        cache: dict[tuple[int, int], tuple[int, str]] = {}
        local_hour = np.empty(len(target), dtype=np.int64)
        local_day: list[str] = []
        for i, (t, off) in enumerate(zip(target, offsets, strict=True)):
            key = (int(t), int(off))
            if key not in cache:
                cal = calendar_at(a.series.hour_at(int(t)), int(off), "US")
                cache[key] = (cal.local_hour, cal.local_day.isoformat())
            local_hour[i], day = cache[key]
            local_day.append(day)
        frame = rows.with_columns(
            pl.Series("actual", actual),
            pl.Series("operator", operator),
            pl.Series("naive", naive),
            pl.Series("local_hour", local_hour),
            pl.Series("local_day", local_day).str.to_date(),
        )
        # The target day is the first full local day after the origin: 24 horizons on one local date.
        per_origin = frame.group_by(["origin", "local_day"]).agg(
            pl.len().alias("hours"), pl.col("horizon").min().alias("first_h")
        )
        full = (
            per_origin.filter(pl.col("hours") == 24)
            .sort(["origin", "first_h"])
            .group_by("origin", maintain_order=True)
            .agg(pl.col("local_day").first().alias("target_day"))
        )
        frame = frame.join(full, on="origin", how="left").with_columns(
            (pl.col("origin") - pl.duration(hours=1)).dt.date().alias("origin_day")
        )
        frames.append(frame)
    return pl.concat(frames)


def unscored_share(scoring: pl.DataFrame) -> float:
    if scoring.height == 0:
        return 1.0
    return (
        float(scoring.filter(pl.col("actual").is_null() | pl.col("actual").is_nan()).height) / scoring.height
    )


def as_of_position(data: PanelData, authority: str, when: datetime) -> int:
    return data.authorities[authority].series.position(when)
