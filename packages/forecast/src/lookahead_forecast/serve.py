"""Model exports and the served model: what the API loads to issue a forecast.

The backtest leaves each backend fitted through the end of the test year; the export writes
what a forecast needs and nothing else. For own: per authority the standardization, the
solved coefficients, the thresholds, the penalty, the conformal offsets and the typical
size. For gbm: the last refit's booster file, the feature names, the authority and region
codes and the interval widening. The served model reads an export and a serving bundle (the
recent hours of demand and weather per authority) and issues a forecast at the latest origin
the bundle allows: the last hour of demand that still has 48 hours of weather after it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from lookahead_core.config import POLICY, QUANTILE_LEVELS
from lookahead_features.build import FeatureSpec, design
from lookahead_features.frame import HOUR, SeriesIndex

from lookahead_forecast.conformal import IntervalConformal, RelativeConformal
from lookahead_forecast.interface import QUANTILE_COLUMNS, ForecastSpec, sort_quantiles

BUNDLE_HOURS = 24 * 21
"""Hours of demand kept per authority in the serving bundle; three weeks covers every lag."""


def export_own(fitted: Any, data: Any, spec: ForecastSpec, path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "backend": "own",
        "version": f"own-{spec.spec_hash[:8]}",
        "spec_hash": spec.spec_hash,
        "spec": spec.model_dump(mode="json"),
        "data_source": data.data_source,
        "levels": list(spec.levels),
        "bucket_hours": spec.conformal_bucket_hours,
        "fitted_through": data.test_end.date().isoformat(),
        "authorities": {},
    }
    for authority in data.names:
        state = fitted.states[authority]
        conformal = fitted.conformal[authority]
        a = data.authorities[authority]
        center, scale, rows = _residual_scale(fitted.validation.get(authority))
        payload["authorities"][authority] = {
            "residual_center": center,
            "residual_scale": scale,
            "residual_rows": rows,
            "names": state.names,
            "mean": state.mean.tolist(),
            "std": state.std.tolist(),
            "beta": state.solve().tolist(),
            "penalty": state.penalty,
            "heating_threshold_c": state.threshold_heating,
            "cooling_threshold_c": state.threshold_cooling,
            "offsets": conformal.offsets.tolist(),
            "typical_mw": a.typical_mw,
            "region": a.region,
            "training_rows": int(state.rows),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _residual_scale(run: Any) -> tuple[float, float, int]:
    """Median and scaled median absolute deviation of the relative residual at horizons 1 to 24 over
    the validation year: what the detector standardizes with."""
    if run is None:
        return 0.0, 0.0, 0
    keep = run.horizon <= 24
    pred = run.pred_ratio[keep]
    actual = run.actual_ratio[keep]
    ok = np.isfinite(pred) & (pred > 0) & np.isfinite(actual)
    r = (actual[ok] - pred[ok]) / pred[ok]
    if len(r) < 100:
        return 0.0, 0.0, int(len(r))
    center = float(np.median(r))
    return center, float(1.4826 * np.median(np.abs(r - center))), int(len(r))


def export_gbm(fitted: Any, data: Any, spec: ForecastSpec, path: Path) -> dict[str, Any]:
    refits = [k for k in fitted.boosters if k != "calibration"]
    key = refits[-1] if refits else "calibration"
    booster = fitted.boosters[key][0]
    # The universal binary format: a fifth the size of the JSON form for the same trees.
    booster_path = path.with_suffix(".booster.ubj")
    path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(booster_path))
    codes = {a: i for i, a in enumerate(data.names)}
    regions = sorted({data.authorities[a].region for a in data.names})
    payload: dict[str, Any] = {
        "backend": "gbm",
        "version": f"gbm-{spec.spec_hash[:8]}",
        "spec_hash": spec.spec_hash,
        "spec": spec.model_dump(mode="json"),
        "data_source": data.data_source,
        "levels": list(spec.levels),
        "bucket_hours": spec.conformal_bucket_hours,
        "fitted_through": key,
        "booster": booster_path.name,
        "names": fitted.names,
        "codes": codes,
        "region_codes": {r: i for i, r in enumerate(regions)},
        "widening": fitted.conformal.widening.tolist(),
        "authorities": {
            a: {"typical_mw": data.authorities[a].typical_mw, "region": data.authorities[a].region}
            for a in data.names
        },
    }
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def write_bundle(data: Any, path: Path) -> pl.DataFrame:
    """The recent hours of demand and weather per authority the API forecasts from."""
    frames = []
    for authority in data.names:
        a = data.authorities[authority]
        n = len(a.series.values)
        start = max(0, n - BUNDLE_HOURS)
        hours = [a.series.hour_at(i) for i in range(start, n)]
        frames.append(
            pl.DataFrame(
                {
                    "authority": [authority] * (n - start),
                    "utc_hour": pl.Series(hours, dtype=pl.Datetime("us", "UTC")),
                    "demand": a.series.values[start:n],
                    "temperature_c": a.temperature[start:n],
                    "humidity_pct": a.humidity[start:n],
                    "utc_offset_hours": a.offsets[start:n].astype(np.int64),
                    "forecast_operator": a.operator[start:n],
                }
            )
        )
    bundle = pl.concat(frames)
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_parquet(path)
    return bundle


@dataclass
class IssuedForecast:
    authority: str
    origin: datetime
    horizons: list[int]
    target_hours: list[datetime]
    quantiles: np.ndarray
    """Rows by levels, megawatts."""
    model_version: str
    backend: str
    spec_hash: str


class ServedModel:
    """An export plus a bundle: issues a forecast for one authority at the latest origin the bundle allows."""

    def __init__(self, export_path: Path, bundle_path: Path) -> None:
        self.payload = json.loads(export_path.read_text(encoding="utf-8"))
        self.backend = str(self.payload["backend"])
        self.version = str(self.payload["version"])
        self.spec_hash = str(self.payload["spec_hash"])
        self.spec = ForecastSpec.model_validate(self.payload["spec"])
        self.bundle = pl.read_parquet(bundle_path)
        self.levels = tuple(float(q) for q in self.payload["levels"])
        self._booster: Any = None
        if self.backend == "gbm":
            import xgboost as xgb

            self._booster = xgb.Booster()
            self._booster.load_model(str(export_path.with_name(str(self.payload["booster"]))))

    @property
    def authorities(self) -> list[str]:
        return sorted(self.bundle["authority"].unique().to_list())

    def latest_origin(self, authority: str) -> datetime:
        rows = self.bundle.filter(pl.col("authority") == authority).sort("utc_hour")
        demand_hours = rows.filter(pl.col("demand").is_not_null() & pl.col("demand").is_not_nan())["utc_hour"]
        weather_hours = rows.filter(
            pl.col("temperature_c").is_not_null() & pl.col("temperature_c").is_not_nan()
        )["utc_hour"]
        if demand_hours.is_empty() or weather_hours.is_empty():
            raise ValueError(f"no demand or weather for {authority} in the bundle")
        last_demand = demand_hours.max()
        last_weather = weather_hours.max()
        assert isinstance(last_demand, datetime) and isinstance(last_weather, datetime)
        candidate = min(last_demand, last_weather - HOUR * POLICY.horizons)
        # Origins are issued at the policy hour, so the latest origin is the last such hour at or before the candidate.
        candidate = candidate.replace(minute=0, second=0, microsecond=0)
        while candidate.hour != POLICY.issue_hour_utc:
            candidate -= HOUR
        return candidate

    def issue(self, authority: str, origin: datetime | None = None) -> IssuedForecast:
        if authority not in self.authorities:
            raise KeyError(authority)
        rows = self.bundle.filter(pl.col("authority") == authority).sort("utc_hour")
        origin = origin or self.latest_origin(authority)
        if origin.tzinfo is None:
            origin = origin.replace(tzinfo=UTC)
        series = SeriesIndex.from_panel(rows.with_columns(pl.col("demand").cast(pl.Float64)), authority)
        temperature = rows["temperature_c"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
        humidity = rows["humidity_pct"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
        offsets = rows["utc_offset_hours"].cast(pl.Int64).to_numpy()
        horizons = np.arange(1, self.spec.horizons + 1)
        position = series.position(origin)
        if self.backend == "own":
            a = self.payload["authorities"][authority]
            features = self.spec.features.model_copy(
                update={
                    "heating_threshold_c": a["heating_threshold_c"],
                    "cooling_threshold_c": a["cooling_threshold_c"],
                }
            )
            d = design(
                series,
                np.array([position]),
                horizons,
                offsets,
                temperature,
                humidity,
                features,
                float(a["typical_mw"]),
            )
            z = (d.x - np.asarray(a["mean"])) / np.asarray(a["std"])
            z[:, 0] = 1.0
            point = z @ np.asarray(a["beta"])
            relative = RelativeConformal(
                levels=self.levels,
                bucket_hours=int(self.payload["bucket_hours"]),
                offsets=np.asarray(a["offsets"]),
                calibration_rows=0,
            )
            q = relative.apply(point, d.horizon)
            scale = d.scale
            horizon = d.horizon
        else:
            from lookahead_forecast.gbm import _authority_design
            from lookahead_forecast.interface import AuthorityData

            a = self.payload["authorities"][authority]
            ad = AuthorityData(
                series=series,
                temperature=temperature,
                humidity=humidity,
                offsets=offsets,
                operator=np.full(len(temperature), np.nan),
                region=str(a["region"]),
                typical_mw=float(a["typical_mw"]),
            )
            code = int(self.payload["codes"][authority])
            region_code = int(self.payload["region_codes"][str(a["region"])])
            ad_design = _authority_design(ad, code, region_code, np.array([position]), self.spec)
            raw = np.asarray(self._booster.inplace_predict(ad_design.x))
            interval = IntervalConformal(
                levels=self.levels,
                bucket_hours=int(self.payload["bucket_hours"]),
                widening=np.asarray(self.payload["widening"]),
                calibration_rows=0,
            )
            q = interval.apply(sort_quantiles(raw), ad_design.horizon)
            scale = ad_design.scale
            horizon = ad_design.horizon
        mw = sort_quantiles(q * scale[:, None])
        _ = horizon
        targets = [origin + HOUR * int(h) for h in horizons]
        return IssuedForecast(
            authority=authority,
            origin=origin,
            horizons=[int(h) for h in horizons],
            target_hours=targets,
            quantiles=mw,
            model_version=self.version,
            backend=self.backend,
            spec_hash=self.spec_hash,
        )

    def actual(self, authority: str, hour: datetime) -> float | None:
        rows = self.bundle.filter((pl.col("authority") == authority) & (pl.col("utc_hour") == hour))
        if rows.height == 0:
            return None
        value = rows["demand"][0]
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        return float(value)


def quantile_payload(issued: IssuedForecast) -> list[dict[str, Any]]:
    return [
        {
            "horizon": h,
            "target_hour": t.isoformat(),
            **{c: float(issued.quantiles[i, k]) for k, c in enumerate(QUANTILE_COLUMNS)},
        }
        for i, (h, t) in enumerate(zip(issued.horizons, issued.target_hours, strict=True))
    ]


def levels_for_columns() -> dict[str, float]:
    return dict(zip(QUANTILE_COLUMNS, QUANTILE_LEVELS, strict=True))


def days_ago(when: datetime) -> float:
    return (datetime.now(UTC) - when) / timedelta(days=1)


__all__ = [
    "ServedModel",
    "IssuedForecast",
    "export_own",
    "export_gbm",
    "write_bundle",
    "quantile_payload",
    "FeatureSpec",
]
