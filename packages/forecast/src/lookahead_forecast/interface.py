"""One interface for every backend, and the data container they all read.

``fit(data, spec, train_end) -> Fitted`` and ``predict(fitted, requests) -> Predictions``.
A backend sees the whole panel but must only use hours at or before each request's origin;
the design builder checks every lag, the leakage test recomputes rows through the frame, and
``test_future_is_not_read`` perturbs everything after the last origin and asserts the
forecasts do not move. Every prediction carries the backend, the spec hash and the data
source, so no figure can lose track of what produced it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

import numpy as np
import polars as pl
from lookahead_core.config import POLICY, QUANTILE_LEVELS
from lookahead_core.hashing import design_hash
from lookahead_core.model import StrictModel
from lookahead_features.build import FeatureSpec
from lookahead_features.frame import HOUR, SeriesIndex

QUANTILE_COLUMNS = tuple(f"q{int(round(q * 100)):02d}" for q in QUANTILE_LEVELS)


class ForecastSpec(StrictModel):
    backend: str
    features: FeatureSpec = FeatureSpec()
    ridge_penalty: float = 1.0
    horizons: int = POLICY.horizons
    levels: tuple[float, ...] = QUANTILE_LEVELS
    conformal_bucket_hours: int = POLICY.conformal_horizon_bucket_hours
    gbm_rounds: int = 250
    gbm_depth: int = 7
    gbm_learning_rate: float = 0.08
    gbm_min_child_weight: int = 50
    gbm_training_window_days: int = POLICY.gbm_training_window_days
    gbm_refit_months: int = POLICY.gbm_refit_months
    seed: int = 13

    @property
    def spec_hash(self) -> str:
        return design_hash(self.model_dump(mode="json"))


@dataclass(frozen=True)
class AuthorityData:
    series: SeriesIndex
    temperature: np.ndarray
    humidity: np.ndarray
    offsets: np.ndarray
    operator: np.ndarray
    """The operator's published day ahead forecast aligned with the series positions, NaN where missing."""
    region: str
    typical_mw: float = 1.0
    """The mean demand over the training window; a per authority constant the weather columns are scaled to."""


@dataclass(frozen=True)
class PanelData:
    """Every authority's aligned arrays, the source they came from and the windows."""

    authorities: dict[str, AuthorityData]
    data_source: str
    training_start: datetime
    validation_start: datetime
    test_start: datetime
    test_end: datetime
    """Inclusive: the last day of the test period."""
    truth: dict[str, np.ndarray] = field(default_factory=dict)
    """The simulator's true demand per authority, aligned with the series; empty on real data."""

    @property
    def names(self) -> list[str]:
        return sorted(self.authorities)

    def origins(self, start: datetime, end: datetime, authority: str) -> np.ndarray:
        """Positions of every daily origin at the issue hour from start to end inclusive, within the series."""
        series = self.authorities[authority].series
        first = datetime(start.year, start.month, start.day, POLICY.issue_hour_utc, tzinfo=UTC)
        out: list[int] = []
        day = first
        while day <= end:
            if series.first_hour + HOUR * 200 <= day <= series.last_hour:
                out.append(series.position(day))
            day += timedelta(days=1)
        return np.asarray(out, dtype=np.int64)

    @classmethod
    def from_frames(
        cls,
        panel: pl.DataFrame,
        weather: pl.DataFrame | None,
        windows: dict[str, str | int],
        data_source: str,
        temperature_column: str = "temperature_c",
        humidity_column: str = "humidity_pct",
    ) -> PanelData:
        authorities: dict[str, AuthorityData] = {}
        columns = set(panel.columns)
        validation_start = datetime.fromisoformat(str(windows["validation_start"])).replace(tzinfo=UTC)
        for name in sorted(panel["authority"].unique().to_list()):
            rows = panel.filter(pl.col("authority") == name).sort("utc_hour")
            series = SeriesIndex.from_panel(rows, name)
            n = len(series.values)
            if weather is not None:
                joined = rows.select("utc_hour").join(
                    weather.filter(pl.col("authority") == name).select(
                        "utc_hour", temperature_column, humidity_column
                    ),
                    on="utc_hour",
                    how="left",
                )
                temperature = joined[temperature_column].cast(pl.Float64).fill_null(float("nan")).to_numpy()
                humidity = joined[humidity_column].cast(pl.Float64).fill_null(float("nan")).to_numpy()
            elif temperature_column in columns:
                temperature = rows[temperature_column].cast(pl.Float64).fill_null(float("nan")).to_numpy()
                humidity = rows[humidity_column].cast(pl.Float64).fill_null(float("nan")).to_numpy()
            else:
                temperature = np.full(n, np.nan)
                humidity = np.full(n, np.nan)
            offsets = (
                rows["utc_offset_hours"].cast(pl.Int64).fill_null(0).to_numpy()
                if "utc_offset_hours" in columns
                else np.zeros(n, dtype=np.int64)
            )
            operator = (
                rows["forecast_operator"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
                if "forecast_operator" in columns
                else np.full(n, np.nan)
            )
            region = str(rows["region"][0]) if "region" in columns else "none"
            training_rows = rows.filter(pl.col("utc_hour") < validation_start)
            typical = training_rows["demand"].mean()
            typical_mw = float(typical) if isinstance(typical, int | float) and typical > 0 else 1.0
            authorities[name] = AuthorityData(
                series=series,
                temperature=np.asarray(temperature, dtype=np.float64),
                humidity=np.asarray(humidity, dtype=np.float64),
                offsets=np.asarray(offsets, dtype=np.int64),
                operator=np.asarray(operator, dtype=np.float64),
                region=region,
                typical_mw=typical_mw,
            )

        def day(key: str) -> datetime:
            value = str(windows[key])
            return datetime.fromisoformat(value).replace(tzinfo=UTC)

        truth: dict[str, np.ndarray] = {}
        if "demand_true" in columns:
            for name in authorities:
                rows = panel.filter(pl.col("authority") == name).sort("utc_hour")
                truth[name] = rows["demand_true"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
        return cls(
            authorities=authorities,
            data_source=data_source,
            training_start=day("training_start"),
            validation_start=day("validation_start"),
            test_start=day("test_start"),
            test_end=day("test_end"),
            truth=truth,
        )


@dataclass(frozen=True)
class Request:
    authority: str
    origin_positions: np.ndarray


@dataclass
class Predictions:
    """Long frame: authority, origin, horizon, target_hour, the quantile columns in MW, backend, spec_hash, data_source."""

    frame: pl.DataFrame
    backend: str
    spec_hash: str
    data_source: str
    fits: int = 0
    """How many model fits the run performed; a did the step run figure."""
    origins: int = 0
    notes: dict[str, float] = field(default_factory=dict)


class Forecaster(Protocol):
    """``fit`` returns the backend's own fitted object; ``predict`` takes it back. Each backend's
    fitted type carries ``backend`` and ``spec_hash`` so a prediction can never lose its provenance."""

    name: str

    def fit(self, data: PanelData, spec: ForecastSpec, train_end: datetime) -> Any: ...

    def predict(
        self, fitted: Any, data: PanelData, spec: ForecastSpec, requests: list[Request]
    ) -> Predictions: ...


def empty_predictions(backend: str, spec_hash: str, data_source: str) -> Predictions:
    schema: dict[str, pl.DataType] = {
        "authority": pl.Utf8(),
        "origin": pl.Datetime("us", "UTC"),
        "horizon": pl.Int64(),
        "target_hour": pl.Datetime("us", "UTC"),
        **{c: pl.Float64() for c in QUANTILE_COLUMNS},
    }
    return Predictions(
        frame=pl.DataFrame(schema=schema), backend=backend, spec_hash=spec_hash, data_source=data_source
    )


def rows_to_frame(
    authority: str,
    series: SeriesIndex,
    origin_position: np.ndarray,
    horizon: np.ndarray,
    quantiles: np.ndarray,
) -> pl.DataFrame:
    """Assemble prediction rows; ``quantiles`` is rows by levels in MW, already sorted across levels."""
    origins = [series.hour_at(int(p)) for p in origin_position]
    targets = [series.hour_at(int(p + h)) for p, h in zip(origin_position, horizon, strict=True)]
    frame = pl.DataFrame(
        {
            "authority": [authority] * len(horizon),
            "origin": pl.Series(origins, dtype=pl.Datetime("us", "UTC")),
            "horizon": horizon.astype(np.int64),
            "target_hour": pl.Series(targets, dtype=pl.Datetime("us", "UTC")),
            **{c: quantiles[:, i] for i, c in enumerate(QUANTILE_COLUMNS)},
        }
    )
    return frame


def sort_quantiles(q: np.ndarray) -> np.ndarray:
    """Quantile crossing is removed by sorting each row across levels."""
    return np.sort(q, axis=1)
