"""The own backend: one ridge regression per authority on the point in time design.

Fourier terms for the day, the week and the year, temperature splines with heating and
cooling thresholds chosen per authority on the validation year, holiday and weekend flags,
and the lags available at each horizon, all as ratios to the mean of the week ending at the
origin. The fit expands at every origin: the Gram matrix and the moment vector are updated
with the rows whose targets have become known, and the ridge system is solved again, so
each day's forecast uses everything up to its origin and nothing after it.

Quantiles come from conformal residual quantiles per horizon bucket, measured on the
validation year with the same expanding procedure, and frozen before the test year starts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from lookahead_core.config import POLICY
from lookahead_features.build import Design, FeatureSpec, design, feature_names, with_thresholds

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


@dataclass
class RidgeState:
    """The expanding fit of one authority: standardization frozen at fit, Gram and moments so far."""

    names: list[str]
    mean: np.ndarray
    std: np.ndarray
    gram: np.ndarray
    moment: np.ndarray
    rows: int
    frontier: int
    """Every design row whose target position is at or below the frontier has been added."""
    penalty: float
    threshold_heating: float
    threshold_cooling: float

    def standardize(self, x: np.ndarray) -> np.ndarray:
        z: np.ndarray = (x - self.mean) / self.std
        z[:, 0] = 1.0
        return z

    def add(self, x: np.ndarray, y: np.ndarray) -> None:
        z = self.standardize(x)
        self.gram += z.T @ z
        self.moment += z.T @ y
        self.rows += len(y)

    def solve(self) -> np.ndarray:
        p = self.gram.shape[0]
        reg = self.penalty * np.eye(p)
        reg[0, 0] = 0.0
        return np.linalg.solve(self.gram + reg, self.moment)


@dataclass
class OwnFitted:
    backend: str
    spec_hash: str
    states: dict[str, RidgeState]
    conformal: dict[str, RelativeConformal]
    designs: dict[str, DesignCache]
    chosen: dict[str, dict[str, float]] = field(default_factory=dict)
    search: dict[str, list[dict[str, float]]] = field(default_factory=dict)
    fits: int = 0


@dataclass
class DesignCache:
    """The design of one authority for every daily origin, ordered by target position."""

    x: np.ndarray
    y_ratio: np.ndarray
    scale: np.ndarray
    origin_position: np.ndarray
    target_position: np.ndarray
    horizon: np.ndarray
    usable: np.ndarray
    order_by_target: np.ndarray


def _all_origins(data: PanelData, authority: str) -> np.ndarray:
    return data.origins(data.training_start, data.test_end, authority)


def build_cache(
    a: AuthorityData, origins: np.ndarray, spec: ForecastSpec, features: FeatureSpec
) -> DesignCache:
    horizons = np.arange(1, spec.horizons + 1)
    d = design(a.series, origins, horizons, a.offsets, a.temperature, a.humidity, features)
    return cache_from_design(a, d)


def cache_from_design(a: AuthorityData, d: Design) -> DesignCache:
    y = np.full(len(d.horizon), np.nan)
    inside = d.target_position < len(a.series.values)
    y[inside] = a.series.values[d.target_position[inside]]
    with np.errstate(invalid="ignore", divide="ignore"):
        y_ratio = np.where(d.usable, y / np.where(d.usable, d.scale, 1.0), np.nan)
    return DesignCache(
        x=d.x,
        y_ratio=y_ratio,
        scale=d.scale,
        origin_position=d.origin_position,
        target_position=d.target_position,
        horizon=d.horizon,
        usable=d.usable,
        order_by_target=np.argsort(d.target_position, kind="stable"),
    )


def _initial_state(
    cache: DesignCache, names: list[str], train_end_position: int, penalty: float, th: float, tc: float
) -> RidgeState:
    rows = cache.usable & np.isfinite(cache.y_ratio) & (cache.target_position <= train_end_position)
    x = cache.x[rows]
    if len(x) < 10 * x.shape[1]:
        raise ValueError(f"only {len(x)} usable training rows for {x.shape[1]} features")
    mean = x.mean(axis=0)
    std = x.std(axis=0)
    std[std < 1e-9] = 1.0
    mean[0], std[0] = 0.0, 1.0
    state = RidgeState(
        names=names,
        mean=mean,
        std=std,
        gram=np.zeros((x.shape[1], x.shape[1])),
        moment=np.zeros(x.shape[1]),
        rows=0,
        frontier=train_end_position,
        penalty=penalty,
        threshold_heating=th,
        threshold_cooling=tc,
    )
    state.add(x, cache.y_ratio[rows])
    return state


def _advance(state: RidgeState, cache: DesignCache, up_to_position: int) -> None:
    """Add every row whose target has become known since the frontier, then move the frontier."""
    if up_to_position <= state.frontier:
        return
    rows = (
        cache.usable
        & np.isfinite(cache.y_ratio)
        & (cache.target_position > state.frontier)
        & (cache.target_position <= up_to_position)
    )
    if rows.any():
        state.add(cache.x[rows], cache.y_ratio[rows])
    state.frontier = up_to_position


def _predict_rows(state: RidgeState, cache: DesignCache, rows: np.ndarray, beta: np.ndarray) -> np.ndarray:
    z = state.standardize(cache.x[rows])
    out: np.ndarray = z @ beta
    return out


def _rolling(
    state: RidgeState, cache: DesignCache, origins: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int]:
    """Expanding fit over the origins in order; returns row indices, median ratio predictions, actual ratios, horizons, fits."""
    out_rows: list[np.ndarray] = []
    out_pred: list[np.ndarray] = []
    fits = 0
    origin_rows = {int(o): np.flatnonzero(cache.origin_position == o) for o in origins}
    for o in sorted(int(v) for v in origins):
        _advance(state, cache, o)
        beta = state.solve()
        fits += 1
        rows = origin_rows[o]
        out_rows.append(rows)
        out_pred.append(_predict_rows(state, cache, rows, beta))
    rows_all = np.concatenate(out_rows) if out_rows else np.zeros(0, dtype=np.int64)
    pred_all = np.concatenate(out_pred) if out_pred else np.zeros(0)
    return rows_all, pred_all, cache.y_ratio[rows_all], cache.horizon[rows_all], fits


def _static_validation_mapes(
    cache: DesignCache,
    names: list[str],
    train_end: int,
    valid_origins: np.ndarray,
    penalties: tuple[float, ...],
    th: float,
    tc: float,
) -> list[float]:
    """One Gram on the training window, one solve per penalty, each scored over the validation origins."""
    state = _initial_state(cache, names, train_end, penalties[0], th, tc)
    rows = np.isin(cache.origin_position, valid_origins) & cache.usable & np.isfinite(cache.y_ratio)
    actual = cache.y_ratio[rows]
    ok = actual > 0
    out: list[float] = []
    for penalty in penalties:
        state.penalty = penalty
        beta = state.solve()
        pred = _predict_rows(state, cache, rows, beta)
        out.append(float(np.mean(np.abs(pred[ok] - actual[ok]) / actual[ok])))
    return out


class OwnForecaster:
    name = "own"

    def fit(self, data: PanelData, spec: ForecastSpec, train_end: datetime) -> OwnFitted:
        """Choose thresholds and the penalty on validation, calibrate the conformal offsets with the
        expanding procedure over the validation year, and leave every state at the validation end."""
        states: dict[str, RidgeState] = {}
        conformal: dict[str, RelativeConformal] = {}
        designs: dict[str, DesignCache] = {}
        chosen: dict[str, dict[str, float]] = {}
        search: dict[str, list[dict[str, float]]] = {}
        fits = 0
        for authority in data.names:
            a = data.authorities[authority]
            origins = _all_origins(data, authority)
            training_end_position = a.series.position(data.validation_start) - 1
            valid_origins = data.origins(data.validation_start, data.test_start, authority)
            valid_origins = valid_origins[valid_origins < a.series.position(data.test_start)]
            best: tuple[float, float, float, float] | None = None
            grid: list[dict[str, float]] = []
            base_features = spec.features
            horizons = np.arange(1, spec.horizons + 1)
            base_design = design(
                a.series, origins, horizons, a.offsets, a.temperature, a.humidity, base_features
            )
            n_hours = len(a.series.values)
            for th in POLICY.heating_thresholds_c:
                for tc in POLICY.cooling_thresholds_c:
                    if tc < th:
                        continue
                    features = base_features.model_copy(
                        update={"heating_threshold_c": th, "cooling_threshold_c": tc}
                    )
                    cache = cache_from_design(
                        a, with_thresholds(base_design, a.temperature, a.humidity, n_hours, features)
                    )
                    names = feature_names(features)
                    mapes = _static_validation_mapes(
                        cache, names, training_end_position, valid_origins, POLICY.ridge_penalties, th, tc
                    )
                    fits += len(mapes)
                    for penalty, mape in zip(POLICY.ridge_penalties, mapes, strict=True):
                        grid.append(
                            {"heating": th, "cooling": tc, "penalty": penalty, "validation_mape": mape}
                        )
                        if best is None or mape < best[0]:
                            best = (mape, th, tc, penalty)
            assert best is not None
            _, th, tc, penalty = best
            features = base_features.model_copy(update={"heating_threshold_c": th, "cooling_threshold_c": tc})
            cache = build_cache(a, origins, spec, features)
            names = feature_names(features)
            state = _initial_state(cache, names, training_end_position, penalty, th, tc)
            rows, pred, actual, horizons, n_fits = _rolling(state, cache, valid_origins)
            fits += n_fits
            conformal[authority] = calibrate_relative(
                pred, actual, horizons, spec.levels, spec.conformal_bucket_hours
            )
            states[authority] = state
            designs[authority] = cache
            chosen[authority] = {
                "heating_threshold_c": th,
                "cooling_threshold_c": tc,
                "ridge_penalty": penalty,
                "validation_mape": best[0],
            }
            search[authority] = grid
        return OwnFitted(
            backend=self.name,
            spec_hash=spec.spec_hash,
            states=states,
            conformal=conformal,
            designs=designs,
            chosen=chosen,
            search=search,
            fits=fits,
        )

    def predict(
        self, fitted: OwnFitted, data: PanelData, spec: ForecastSpec, requests: list[Request]
    ) -> Predictions:
        frames = []
        fits = 0
        origins_total = 0
        for request in requests:
            a = data.authorities[request.authority]
            state = fitted.states[request.authority]
            cache = fitted.designs[request.authority]
            rows, pred, _, horizons, n_fits = _rolling(state, cache, request.origin_positions)
            fits += n_fits
            origins_total += len(request.origin_positions)
            quantiles = fitted.conformal[request.authority].apply(pred, horizons)
            mw = sort_quantiles(quantiles * cache.scale[rows][:, None])
            mw[~cache.usable[rows]] = np.nan
            frames.append(
                rows_to_frame(
                    request.authority, a.series, cache.origin_position[rows], cache.horizon[rows], mw
                )
            )
        import polars as pl

        frame = pl.concat(frames) if frames else pl.DataFrame()
        return Predictions(
            frame=frame,
            backend=self.name,
            spec_hash=spec.spec_hash,
            data_source=data.data_source,
            fits=fits,
            origins=origins_total,
        )


def coefficient_table(fitted: OwnFitted, authority: str) -> list[tuple[str, float]]:
    state = fitted.states[authority]
    beta = state.solve()
    return list(zip(state.names, (float(b) for b in beta), strict=True))


def relative_error_is_finite(value: float) -> bool:
    return math.isfinite(value)
