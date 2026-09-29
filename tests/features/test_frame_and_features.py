"""The point in time frame refuses reads past the origin, the fast design matches the frame
row by row on a sample, and a lag one hour short of the horizon is rejected by both."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from lookahead_features.build import (
    FeatureSpec,
    design,
    feature_names,
    is_holiday,
    row_from_frame,
    same_hour_lag,
)
from lookahead_features.frame import LeakageError, PointInTimeFrame, SeriesIndex

START = datetime(2024, 1, 1, 1, tzinfo=UTC)
HOURS = 24 * 120


def _series(seed: int = 3, holes: int = 5) -> tuple[SeriesIndex, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    hours = np.arange(HOURS)
    values = (
        10_000
        + 2_000 * np.sin(2 * np.pi * hours / 24)
        + 500 * np.sin(2 * np.pi * hours / 168)
        + rng.normal(0, 100, HOURS)
    )
    for hole in rng.choice(HOURS, holes, replace=False):
        values[hole] = np.nan
    stamps = [START + timedelta(hours=int(i)) for i in hours]
    panel = pl.DataFrame({"authority": ["A"] * HOURS, "utc_hour": stamps, "demand": values}).with_columns(
        pl.col("utc_hour").dt.replace_time_zone("UTC")
    )
    series = SeriesIndex.from_panel(panel, "A")
    temperature = 15 + 10 * np.sin(2 * np.pi * hours / 24) + rng.normal(0, 1, HOURS)
    humidity = np.clip(60 + rng.normal(0, 10, HOURS), 0, 100)
    offsets = np.full(HOURS, -5, dtype=np.int64)
    return series, temperature, humidity, offsets


def test_frame_refuses_reads_after_the_origin() -> None:
    series, *_ = _series()
    origin = START + timedelta(hours=24 * 60 - 1)
    frame = PointInTimeFrame(series, origin)
    assert frame.at(origin) == pytest.approx(series.values[24 * 60 - 1])
    with pytest.raises(LeakageError):
        frame.at(origin + timedelta(hours=1))
    with pytest.raises(LeakageError):
        frame.before(origin + timedelta(hours=1))
    earlier = frame.before(origin - timedelta(hours=48))
    assert earlier.visible_hours == frame.visible_hours - 48
    assert len(frame.history(168)) == 168
    assert np.isnan(PointInTimeFrame(series, START + timedelta(hours=10)).history(168)[0])


def test_the_deliberately_leaky_lag_is_refused_by_frame_and_design() -> None:
    series, temperature, humidity, offsets = _series()
    origin = START + timedelta(hours=24 * 60 - 1)
    frame = PointInTimeFrame(series, origin)
    horizon = 30
    target = origin + timedelta(hours=horizon)
    assert frame.lag(target, horizon) == pytest.approx(frame.at(origin))
    with pytest.raises(LeakageError):
        frame.lag(target, horizon - 1)
    # The design refuses a lag array that reaches past the origin.
    from lookahead_features import build as build_module

    with pytest.raises(LeakageError):
        build_module._assert_available(horizon - 1, horizon)


def test_same_hour_lag_is_24_then_48() -> None:
    assert [same_hour_lag(h) for h in (1, 24, 25, 48)] == [24, 24, 48, 48]


def test_design_matches_the_frame_row_by_row() -> None:
    series, temperature, humidity, offsets = _series()
    spec = FeatureSpec(heating_threshold_c=12.0, cooling_threshold_c=18.0)
    origins = np.array([24 * d - 1 for d in range(30, 110, 7)])
    horizons = np.arange(1, 49)
    d = design(series, origins, horizons, offsets, temperature, humidity, spec, 9_000.0)
    assert d.x.shape == (len(origins) * 48, len(feature_names(spec)))
    assert d.usable.all()
    rng = np.random.default_rng(1)
    for _ in range(60):
        i = int(rng.integers(0, d.x.shape[0]))
        origin = series.hour_at(int(d.origin_position[i]))
        frame = PointInTimeFrame(series, origin)
        h = int(d.horizon[i])
        t = int(d.target_position[i])
        lag_t = t - same_hour_lag(h)
        row, scale = row_from_frame(
            frame, h, -5, float(temperature[t]), float(humidity[t]), spec, 9_000.0, float(temperature[lag_t])
        )
        np.testing.assert_allclose(d.x[i], row, rtol=0, atol=1e-9)
        assert d.scale[i] == pytest.approx(scale)


def test_holes_become_indicators_not_leaks() -> None:
    series, temperature, humidity, offsets = _series(holes=0)
    values = series.values.copy()
    values[24 * 60 - 1 + 5 - 24] = (
        np.nan
    )  # the same hour lag of horizon 5 from the origin at position 24 * 60 - 1
    holed = SeriesIndex(series.authority, series.first_hour, values)
    d = design(
        holed, np.array([24 * 60 - 1]), np.arange(1, 49), offsets, temperature, humidity, FeatureSpec()
    )
    names = feature_names(FeatureSpec())
    col = names.index("same_hour_missing")
    assert d.x[4, col] == 1.0 and d.x[5, col] == 0.0


def test_us_holidays_come_from_the_named_country() -> None:
    from datetime import date

    assert is_holiday(date(2024, 7, 4), "US")
    assert not is_holiday(date(2024, 7, 5), "US")
    assert is_holiday(date(2013, 12, 25), "GB")


def test_series_index_refuses_an_incomplete_grid() -> None:
    stamps = [START, START + timedelta(hours=1), START + timedelta(hours=3)]
    panel = pl.DataFrame(
        {"authority": ["A"] * 3, "utc_hour": stamps, "demand": [1.0, 2.0, 3.0]}
    ).with_columns(pl.col("utc_hour").dt.replace_time_zone("UTC"))
    with pytest.raises(ValueError, match="complete grid"):
        SeriesIndex.from_panel(panel, "A")
