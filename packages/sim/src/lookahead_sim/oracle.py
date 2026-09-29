"""An oracle forecaster with a known error, for grading the harness on certainty.

Its point forecast is the simulator's true demand times one plus an AR(1) error with a
stated standard deviation, so its expected MAPE is known in closed form, and its skill
against the synthetic operator (whose error is stated the same way) is known too. The
harness measures that skill; the recovery study reports the difference and whether the
bootstrap interval covers the known value. Quantiles come from the same relative conformal
step every point forecast gets, so coverage against nominal is graded as well.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import polars as pl
from lookahead_core.seeds import rng
from lookahead_forecast.conformal import RelativeConformal, calibrate_relative
from lookahead_forecast.interface import (
    ForecastSpec,
    PanelData,
    Predictions,
    Request,
    rows_to_frame,
    sort_quantiles,
)

from lookahead_sim.grid import _ar1


def expected_mape(sigma: float, bias: float = 0.0) -> float:
    return sigma * math.sqrt(2 / math.pi) * math.exp(-(bias**2) / (2 * sigma**2)) + bias * math.erf(
        bias / (sigma * math.sqrt(2))
    )


@dataclass
class OracleFitted:
    backend: str
    spec_hash: str
    errors: dict[str, np.ndarray]
    conformal: dict[str, RelativeConformal]
    fits: int


class OracleForecaster:
    name = "oracle"

    def __init__(self, sigma: float = 0.015, phi: float = 0.6, seed: int = 0) -> None:
        self.sigma = sigma
        self.phi = phi
        self.seed = seed

    @property
    def known_mape(self) -> float:
        return expected_mape(self.sigma)

    def _forecast(
        self, data: PanelData, authority: str, errors: np.ndarray, origins: np.ndarray, horizons: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        truth = data.truth[authority]
        o = np.repeat(origins, len(horizons))
        h = np.tile(horizons, len(origins))
        t = o + h
        ok = t < len(truth)
        point = np.full(len(t), np.nan)
        point[ok] = truth[t[ok]] * (1.0 + errors[t[ok]])
        return o, h, point

    def fit(self, data: PanelData, spec: ForecastSpec, train_end: datetime) -> OracleFitted:
        if not data.truth:
            raise ValueError("the oracle needs the simulator's true demand")
        errors: dict[str, np.ndarray] = {}
        conformal: dict[str, RelativeConformal] = {}
        horizons = np.arange(1, spec.horizons + 1)
        for authority in data.names:
            n = len(data.authorities[authority].series.values)
            errors[authority] = _ar1(rng(self.seed, "oracle", authority), n, self.sigma, self.phi)
            origins = data.origins(data.validation_start, data.test_start, authority)
            origins = origins[origins < data.authorities[authority].series.position(data.test_start)]
            o, h, point = self._forecast(data, authority, errors[authority], origins, horizons)
            t = o + h
            actual = np.full(len(t), np.nan)
            values = data.authorities[authority].series.values
            inside = t < len(values)
            actual[inside] = values[t[inside]]
            conformal[authority] = calibrate_relative(
                point, actual, h, spec.levels, spec.conformal_bucket_hours
            )
        return OracleFitted(
            backend=self.name, spec_hash=spec.spec_hash, errors=errors, conformal=conformal, fits=len(errors)
        )

    def predict(
        self, fitted: OracleFitted, data: PanelData, spec: ForecastSpec, requests: list[Request]
    ) -> Predictions:
        horizons = np.arange(1, spec.horizons + 1)
        frames = []
        for request in requests:
            a = data.authorities[request.authority]
            o, h, point = self._forecast(
                data, request.authority, fitted.errors[request.authority], request.origin_positions, horizons
            )
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
