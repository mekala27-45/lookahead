"""The gbm backend: one global gradient boosted model over every authority, with the pinball
loss at the five served levels.

One booster per refit with five outputs, trained on the same point in time design as the own
backend (lags at the horizon's availability, calendar, observed weather) plus the authority
and its region as categorical codes, its typical size, and the scaled temperature, on the
target as a ratio to the origin's scale, so a hundred megawatt authority and a hundred
gigawatt one share one model. The training window is the stated number of days before each
refit, thinned to every third origin day; refits happen at the start of every calendar month
of the test year. Split conformal per horizon bucket, calibrated on the validation year with
the model fitted at the validation start, widens or narrows each interval so the validation
coverage holds.

XGBoost's ``reg:quantileerror`` is used rather than LightGBM's ``quantile``: LightGBM renews
every leaf's value by sorting its residuals each round, which measured at over a second a
round per level on a seventh of the rows, and thirteen refits of five levels was a six hour
job; the pinball objective here trains the five levels together in a fraction of that time.
The reversal from the brief's stack line is in DECISIONS.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import polars as pl
from lookahead_core.config import POLICY
from lookahead_core.seeds import rng
from lookahead_features.build import design, feature_names

from lookahead_forecast.conformal import IntervalConformal, calibrate_interval
from lookahead_forecast.interface import (
    AuthorityData,
    ForecastSpec,
    PanelData,
    Predictions,
    Request,
    rows_to_frame,
    sort_quantiles,
)

EXTRA_COLUMNS = ("authority_code", "region_code", "log_typical_mw", "obs_temperature_scaled")


@dataclass
class AuthorityDesign:
    x: np.ndarray
    """float32 rows by features, the base design plus the extra columns."""
    y_ratio: np.ndarray
    scale: np.ndarray
    origin_position: np.ndarray
    target_position: np.ndarray
    horizon: np.ndarray
    usable: np.ndarray


@dataclass
class GbmFitted:
    backend: str
    spec_hash: str
    names: list[str]
    designs: dict[str, AuthorityDesign]
    conformal: IntervalConformal
    boosters: dict[str, list[object]] = field(default_factory=dict)
    """Refit date (ISO) to the five boosters, in level order."""
    fits: int = 0
    calibration_rows: int = 0
    training_rows_by_refit: dict[str, int] = field(default_factory=dict)


def _authority_design(
    a: AuthorityData, code: int, region_code: int, origins: np.ndarray, spec: ForecastSpec
) -> AuthorityDesign:
    horizons = np.arange(1, spec.horizons + 1)
    d = design(a.series, origins, horizons, a.offsets, a.temperature, a.humidity, spec.features, a.typical_mw)
    n = len(a.series.values)
    y = np.full(len(d.horizon), np.nan)
    inside = d.target_position < n
    y[inside] = a.series.values[d.target_position[inside]]
    with np.errstate(invalid="ignore", divide="ignore"):
        y_ratio = np.where(d.usable, y / np.where(d.usable, d.scale, 1.0), np.nan)
    temp = np.full(len(d.horizon), np.nan)
    temp[inside] = a.temperature[d.target_position[inside]]
    temp = np.where(np.isfinite(temp), temp, 0.0) * d.weather_scaling
    extra = np.stack(
        [
            np.full(len(d.horizon), code, dtype=np.float64),
            np.full(len(d.horizon), region_code, dtype=np.float64),
            np.full(len(d.horizon), np.log(max(a.typical_mw, 1.0))),
            temp,
        ],
        axis=1,
    )
    x = np.concatenate([d.x, extra], axis=1).astype(np.float32)
    return AuthorityDesign(
        x=x,
        y_ratio=y_ratio,
        scale=d.scale,
        origin_position=d.origin_position,
        target_position=d.target_position,
        horizon=d.horizon,
        usable=d.usable,
    )


ORIGIN_DAY_THINNING = 3
"""The global model trains on every third origin day of its window, all horizons, all authorities."""

MAX_BIN = 64


def _params(spec: ForecastSpec, levels: tuple[float, ...], seed: int) -> dict[str, object]:
    return {
        "objective": "reg:quantileerror",
        "quantile_alpha": np.asarray(levels, dtype=np.float64),
        "tree_method": "hist",
        "max_bin": MAX_BIN,
        "learning_rate": spec.gbm_learning_rate,
        "max_depth": spec.gbm_depth,
        "min_child_weight": spec.gbm_min_child_weight,
        "subsample": 0.5,
        "colsample_bytree": 0.8,
        "reg_lambda": 1.0,
        "nthread": 2,
        "seed": seed,
        "verbosity": 0,
    }


def _training_matrix(
    designs: dict[str, AuthorityDesign],
    data: PanelData,
    refit_position_by_authority: dict[str, int],
    window_days: int,
) -> tuple[np.ndarray, np.ndarray]:
    xs = []
    ys = []
    for authority, d in designs.items():
        end = refit_position_by_authority[authority]
        start = end - window_days * 24
        rows = d.usable & np.isfinite(d.y_ratio) & (d.target_position <= end) & (d.origin_position >= start)
        xs.append(d.x[rows])
        ys.append(d.y_ratio[rows])
    x = np.concatenate(xs)
    y = np.concatenate(ys)
    # Sort before any seeded step: bagging draws rows in a fixed order whatever the dict order was.
    order = np.lexsort((x[:, -4], x[:, 0], y))
    return x[order], y[order]


def _train(x: np.ndarray, y: np.ndarray, names: list[str], spec: ForecastSpec, seed: int) -> list[object]:
    import xgboost as xgb

    types = ["c" if n in ("authority_code", "region_code") else "q" for n in names]
    matrix = xgb.QuantileDMatrix(
        x, y, feature_names=names, feature_types=types, max_bin=MAX_BIN, nthread=2, enable_categorical=True
    )
    booster = xgb.train(_params(spec, spec.levels, seed), matrix, num_boost_round=spec.gbm_rounds)
    return [booster]


def _predict(boosters: list[object], x: np.ndarray) -> np.ndarray:
    booster = boosters[0]
    out = np.asarray(booster.inplace_predict(x))  # type: ignore[attr-defined]
    if out.ndim == 1:
        out = out[:, None]
    return out


def month_starts(first: datetime, last: datetime) -> list[datetime]:
    """The first day of every calendar month from the month of ``first`` to the month of ``last``."""
    out = []
    current = datetime(first.year, first.month, 1, tzinfo=first.tzinfo)
    while current <= last:
        out.append(current)
        current = datetime(
            current.year + (current.month // 12), current.month % 12 + 1, 1, tzinfo=first.tzinfo
        )
    return out


class GbmForecaster:
    name = "gbm"

    def fit(self, data: PanelData, spec: ForecastSpec, train_end: datetime) -> GbmFitted:
        names = feature_names(spec.features) + list(EXTRA_COLUMNS)
        codes = {a: i for i, a in enumerate(data.names)}
        regions = sorted({data.authorities[a].region for a in data.names})
        region_codes = {r: i for i, r in enumerate(regions)}
        designs: dict[str, AuthorityDesign] = {}
        for authority in data.names:
            a = data.authorities[authority]
            origins = data.origins(data.training_start, data.test_end, authority)
            designs[authority] = _authority_design(a, codes[authority], region_codes[a.region], origins, spec)
        # The calibration fit: trained on the window before the validation year, scored over it.
        refit = {a: data.authorities[a].series.position(data.validation_start) - 1 for a in data.names}
        x, y = _training_matrix(designs, data, refit, spec.gbm_training_window_days)
        boosters = _train(x, y, names, spec, spec.seed)
        preds = []
        actual = []
        horizons = []
        for authority, d in designs.items():
            a = data.authorities[authority]
            valid = (
                (d.origin_position >= a.series.position(data.validation_start))
                & (d.origin_position < a.series.position(data.test_start))
                & d.usable
            )
            if not valid.any():
                continue
            q = _predict(boosters, d.x[valid])
            preds.append(sort_quantiles(q))
            actual.append(d.y_ratio[valid])
            horizons.append(d.horizon[valid])
        conformal = calibrate_interval(
            np.concatenate(preds),
            np.concatenate(actual),
            np.concatenate(horizons),
            spec.levels,
            spec.conformal_bucket_hours,
        )
        return GbmFitted(
            backend=self.name,
            spec_hash=spec.spec_hash,
            names=names,
            designs=designs,
            conformal=conformal,
            boosters={"calibration": boosters},
            fits=1,
            calibration_rows=conformal.calibration_rows,
            training_rows_by_refit={"calibration": int(len(y))},
        )

    def predict(
        self, fitted: GbmFitted, data: PanelData, spec: ForecastSpec, requests: list[Request]
    ) -> Predictions:
        wanted = {r.authority: set(int(p) for p in r.origin_positions) for r in requests}
        first_origin = min(
            data.authorities[r.authority].series.hour_at(int(r.origin_positions.min())) for r in requests
        )
        last_origin = max(
            data.authorities[r.authority].series.hour_at(int(r.origin_positions.max())) for r in requests
        )
        frames = []
        fits = fitted.fits
        origins_total = 0
        for start in month_starts(first_origin, last_origin):
            end = datetime(start.year + (start.month // 12), start.month % 12 + 1, 1, tzinfo=start.tzinfo)
            key = start.date().isoformat()
            if key not in fitted.boosters:
                refit = {a: data.authorities[a].series.position(start) - 1 for a in data.names}
                x, y = _training_matrix(fitted.designs, data, refit, spec.gbm_training_window_days)
                fitted.boosters[key] = _train(
                    x, y, fitted.names, spec, spec.seed + 100 * len(fitted.boosters)
                )
                fitted.training_rows_by_refit[key] = int(len(y))
                fits += 1
            boosters = fitted.boosters[key]
            for request in requests:
                a = data.authorities[request.authority]
                d = fitted.designs[request.authority]
                positions = [
                    p for p in sorted(wanted[request.authority]) if start <= a.series.hour_at(p) < end
                ]
                if not positions:
                    continue
                rows = np.isin(d.origin_position, np.asarray(positions))
                q = sort_quantiles(_predict(boosters, d.x[rows]))
                q = sort_quantiles(fitted.conformal.apply(q, d.horizon[rows]))
                mw = q * d.scale[rows][:, None]
                mw[~d.usable[rows]] = np.nan
                frames.append(
                    rows_to_frame(request.authority, a.series, d.origin_position[rows], d.horizon[rows], mw)
                )
                origins_total += len(positions)
        fitted.fits = fits
        frame = pl.concat(frames).sort(["authority", "origin", "horizon"]) if frames else pl.DataFrame()
        return Predictions(
            frame=frame,
            backend=self.name,
            spec_hash=spec.spec_hash,
            data_source=data.data_source,
            fits=fits,
            origins=origins_total,
        )


def validation_coverage(
    fitted: GbmFitted, data: PanelData, level_pair: tuple[float, float] = (0.05, 0.95)
) -> float:
    """Share of validation year actuals inside the calibrated interval of the calibration model,
    pooled over authorities and horizons: what the registry's coverage gate reads."""
    boosters = fitted.boosters["calibration"]
    levels = list(fitted.conformal.levels)
    inside = 0
    total = 0
    for authority, d in fitted.designs.items():
        a = data.authorities[authority]
        valid = (
            (d.origin_position >= a.series.position(data.validation_start))
            & (d.origin_position < a.series.position(data.test_start))
            & d.usable
            & np.isfinite(d.y_ratio)
        )
        if not valid.any():
            continue
        q = sort_quantiles(
            fitted.conformal.apply(sort_quantiles(_predict(boosters, d.x[valid])), d.horizon[valid])
        )
        actual = d.y_ratio[valid]
        lo = q[:, levels.index(level_pair[0])]
        hi = q[:, levels.index(level_pair[1])]
        inside += int(np.sum((actual >= lo) & (actual <= hi)))
        total += int(valid.sum())
    if total == 0:
        raise ValueError("no validation rows to measure coverage on")
    return inside / total


def feature_importance(fitted: GbmFitted, key: str = "calibration") -> list[tuple[str, float]]:
    booster = fitted.boosters[key][0]
    scores: dict[str, float] = booster.get_score(importance_type="total_gain")  # type: ignore[attr-defined]
    total = sum(scores.values()) or 1.0
    return sorted(((name, scores.get(name, 0.0) / total) for name in fitted.names), key=lambda kv: -kv[1])


def bagging_seed_check(spec: ForecastSpec) -> int:
    """The seed every booster derives from; a test asserts two runs give identical predictions."""
    return int(rng(spec.seed, "gbm").integers(0, 2**31 - 1))


def days_between(a: datetime, b: datetime) -> int:
    return int((b - a) / timedelta(days=1))


__all__ = ["GbmForecaster", "GbmFitted", "feature_importance", "month_starts", "POLICY"]
