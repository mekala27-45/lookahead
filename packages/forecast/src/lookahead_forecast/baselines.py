"""The two baselines every table carries.

The seasonal naive forecasts each target hour with demand at the same hour one week
earlier (two weeks earlier when that hour was quarantined, the mean of the week before the
origin when both were), and gets quantiles by relative conformal on the validation year like
any other point forecast. The operator's published day ahead forecast is not a model here:
it is read from the data at the target hour and attached to every scoring row by the harness.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import polars as pl
from lookahead_core.config import POLICY
from lookahead_features.frame import LeakageError

from lookahead_forecast.conformal import RelativeConformal, calibrate_relative
from lookahead_forecast.interface import (
    AuthorityData,
    ForecastSpec,
    PanelData,
    Predictions,
    Request,
    rows_to_frame,
    sort_quantiles,
)

LAG = POLICY.seasonal_naive_lag_hours


def naive_point(a: AuthorityData, origin_position: np.ndarray, horizon: np.ndarray) -> np.ndarray:
    """The seasonal naive point forecast for rows of (origin position, horizon), lags checked."""
    if np.any(horizon > LAG):
        raise LeakageError(f"the seasonal naive lag of {LAG} hours does not cover a horizon past it")
    y = a.series.values
    n = len(y)
    t = origin_position + horizon

    def read(position: np.ndarray) -> np.ndarray:
        out = np.full(len(position), np.nan)
        ok = (position >= 0) & (position < n)
        out[ok] = y[position[ok]]
        return out

    first = read(t - LAG)
    second = read(t - 2 * LAG)
    cumsum = np.concatenate([[0.0], np.nancumsum(y)])
    counts = np.concatenate([[0], np.cumsum(np.isfinite(y).astype(np.int64))])
    stop = np.clip(origin_position + 1, 0, n)
    start = np.clip(stop - LAG, 0, n)
    with np.errstate(invalid="ignore", divide="ignore"):
        week_mean = np.where(
            counts[stop] - counts[start] > 0,
            (cumsum[stop] - cumsum[start]) / np.maximum(counts[stop] - counts[start], 1),
            np.nan,
        )
    return np.where(np.isfinite(first), first, np.where(np.isfinite(second), second, week_mean))


@dataclass
class NaiveFitted:
    backend: str
    spec_hash: str
    conformal: dict[str, RelativeConformal]
    fits: int


class SeasonalNaiveForecaster:
    name = "seasonal_naive"

    def fit(self, data: PanelData, spec: ForecastSpec, train_end: datetime) -> NaiveFitted:
        conformal: dict[str, RelativeConformal] = {}
        horizons = np.arange(1, spec.horizons + 1)
        for authority in data.names:
            a = data.authorities[authority]
            origins = data.origins(data.validation_start, data.test_start, authority)
            origins = origins[origins < a.series.position(data.test_start)]
            o = np.repeat(origins, len(horizons))
            h = np.tile(horizons, len(origins))
            pred = naive_point(a, o, h)
            t = o + h
            actual = np.full(len(t), np.nan)
            inside = t < len(a.series.values)
            actual[inside] = a.series.values[t[inside]]
            conformal[authority] = calibrate_relative(
                pred, actual, h, spec.levels, spec.conformal_bucket_hours
            )
        return NaiveFitted(
            backend=self.name, spec_hash=spec.spec_hash, conformal=conformal, fits=len(conformal)
        )

    def predict(
        self, fitted: NaiveFitted, data: PanelData, spec: ForecastSpec, requests: list[Request]
    ) -> Predictions:
        horizons = np.arange(1, spec.horizons + 1)
        frames = []
        for request in requests:
            a = data.authorities[request.authority]
            o = np.repeat(request.origin_positions, len(horizons))
            h = np.tile(horizons, len(request.origin_positions))
            point = naive_point(a, o, h)
            q = fitted.conformal[request.authority].apply(point, h)
            frames.append(rows_to_frame(request.authority, a.series, o, h, sort_quantiles(q)))
        frame = pl.concat(frames) if frames else pl.DataFrame()
        return Predictions(
            frame=frame,
            backend=self.name,
            spec_hash=spec.spec_hash,
            data_source=data.data_source,
            fits=0,
            origins=sum(len(r.origin_positions) for r in requests),
        )


def operator_at(a: AuthorityData, target_position: np.ndarray) -> np.ndarray:
    """The operator's published forecast at the target hours, NaN where it was not published."""
    out = np.full(len(target_position), np.nan)
    ok = (target_position >= 0) & (target_position < len(a.operator))
    out[ok] = a.operator[target_position[ok]]
    return out
