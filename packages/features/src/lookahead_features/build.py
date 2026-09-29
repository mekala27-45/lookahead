"""Point in time features for one (origin, horizon) row, and the same features for many rows at once.

Two builders, one contract. ``row_from_frame`` reads every lag through a PointInTimeFrame,
which raises if a lag reaches past the origin; it is the reference and it is slow.
``design`` builds the same columns for thousands of origins with array indexing and checks
every target relative lag against the horizon before it reads. The leakage test recomputes a
sample of rows through the frame and asserts equality, and asserts that a lag one hour
short of the horizon is refused by both.

Every megawatt feature is a ratio to the scale, the mean of the week ending at the origin, and
the target is predicted as the same ratio, so one model covers authorities from a hundred
megawatts to a hundred gigawatts and seasons from spring to a heat wave. Weather is observed
weather at the target hour, which a real day ahead process does not have; the caveat is in
the column names (``obs_``) and on every figure that uses them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache

import numpy as np
from lookahead_core.model import StrictModel

from lookahead_features.frame import HOUR, LeakageError, PointInTimeFrame, SeriesIndex

SEASONAL_LAG = 168


class FeatureSpec(StrictModel):
    heating_threshold_c: float = 14.0
    cooling_threshold_c: float = 20.0
    fourier_daily: int = 3
    fourier_weekly: int = 2
    fourier_yearly: int = 2
    country: str = "US"
    use_weather: bool = True


def feature_names(spec: FeatureSpec) -> list[str]:
    names = [
        "intercept",
        "r_same_hour",
        "r_same_hour_prev",
        "r_week",
        "r_two_weeks",
        "r_origin",
        "r_mean_24",
        "same_hour_missing",
        "week_missing",
        "horizon_over_24",
        "horizon_share",
        "weekend",
        "holiday",
    ]
    for k in range(1, spec.fourier_daily + 1):
        names += [f"day_sin_{k}", f"day_cos_{k}"]
    for k in range(1, spec.fourier_weekly + 1):
        names += [f"week_sin_{k}", f"week_cos_{k}"]
    for k in range(1, spec.fourier_yearly + 1):
        names += [f"year_sin_{k}", f"year_cos_{k}"]
    if spec.use_weather:
        names += [
            "obs_temperature",
            "obs_heating_degree",
            "obs_cooling_degree",
            "obs_humidity",
            "obs_cooling_x_day_sin",
            "obs_cooling_x_day_cos",
            "obs_heating_x_day_sin",
            "obs_heating_x_day_cos",
            "obs_weather_missing",
        ]
    return names


@lru_cache(maxsize=8)
def _holiday_set(country: str, first_year: int, last_year: int) -> frozenset[date]:
    import holidays as hol

    years = range(first_year, last_year + 1)
    return frozenset(hol.country_holidays(country, years=years).keys())


def is_holiday(day: date, country: str) -> bool:
    return day in _holiday_set(country, day.year - 1, day.year + 1)


def same_hour_lag(horizon: int) -> int:
    """The nearest same hour of day at or before the origin: 24 for horizons 1 to 24, 48 for 25 to 48."""
    return 24 * math.ceil(horizon / 24)


def _assert_available(lag_hours: int, horizon: int) -> None:
    """A target relative lag is readable at the origin only when it reaches at least the horizon back."""
    if lag_hours < horizon:
        raise LeakageError(f"a lag of {lag_hours} hours reaches past the origin for horizon {horizon}")


@dataclass(frozen=True)
class Calendar:
    local_hour: int
    local_day: date
    weekend: bool
    holiday: bool
    day_of_year: int


def calendar_at(target_utc: datetime, offset_hours: int, country: str) -> Calendar:
    local = target_utc + timedelta(hours=int(offset_hours))
    # Hour ending: the hour of day the interval belongs to is the one that ends at this stamp.
    hour = (local.hour - 1) % 24
    day = (local - HOUR).date()
    return Calendar(
        local_hour=hour,
        local_day=day,
        weekend=day.weekday() >= 5,
        holiday=is_holiday(day, country),
        day_of_year=day.timetuple().tm_yday,
    )


def _fourier(value: float, period: float, k: int) -> list[float]:
    out: list[float] = []
    for i in range(1, k + 1):
        angle = 2.0 * math.pi * i * value / period
        out += [math.sin(angle), math.cos(angle)]
    return out


def _ratio(value: float, scale: float) -> float:
    return value / scale if not math.isnan(value) else math.nan


def row_from_frame(
    frame: PointInTimeFrame,
    horizon: int,
    offset_hours: int,
    temperature: float,
    humidity: float,
    spec: FeatureSpec,
) -> tuple[np.ndarray, float]:
    """One feature row through the frame, plus the scale. The reference implementation."""
    target = frame.origin + HOUR * horizon
    week = frame.history(SEASONAL_LAG)
    scale = float(np.nanmean(week)) if np.isfinite(week).any() else math.nan
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("no scale: the week before the origin has no demand")
    same = same_hour_lag(horizon)
    for lag_hours in (same, same + 24, SEASONAL_LAG, 2 * SEASONAL_LAG, horizon):
        _assert_available(lag_hours, horizon)
    r_same = _ratio(frame.lag(target, same), scale)
    r_same_prev = _ratio(frame.lag(target, same + 24), scale)
    r_week = _ratio(frame.lag(target, SEASONAL_LAG), scale)
    r_two_weeks = _ratio(frame.lag(target, 2 * SEASONAL_LAG), scale)
    r_origin = _ratio(frame.lag(target, horizon), scale)
    r_mean_24 = _ratio(float(np.nanmean(frame.history(24))), scale)
    fallback = r_mean_24 if math.isfinite(r_mean_24) else 1.0
    same_missing = float(math.isnan(r_same))
    week_missing = float(math.isnan(r_week))
    cal = calendar_at(target, offset_hours, spec.country)
    values: list[float] = [
        1.0,
        r_same if not math.isnan(r_same) else fallback,
        r_same_prev if not math.isnan(r_same_prev) else fallback,
        r_week if not math.isnan(r_week) else fallback,
        r_two_weeks if not math.isnan(r_two_weeks) else fallback,
        r_origin if not math.isnan(r_origin) else fallback,
        fallback,
        same_missing,
        week_missing,
        float(horizon > 24),
        horizon / 48.0,
        float(cal.weekend),
        float(cal.holiday),
    ]
    values += _fourier(cal.local_hour, 24.0, spec.fourier_daily)
    values += _fourier(cal.local_day.weekday() * 24 + cal.local_hour, 168.0, spec.fourier_weekly)
    values += _fourier(cal.day_of_year, 365.25, spec.fourier_yearly)
    if spec.use_weather:
        values += _weather_columns(temperature, humidity, cal.local_hour, spec)
    return np.asarray(values, dtype=np.float64), scale


def _weather_columns(temperature: float, humidity: float, local_hour: int, spec: FeatureSpec) -> list[float]:
    missing = math.isnan(temperature)
    t = 0.0 if missing else temperature
    hdh = max(spec.heating_threshold_c - t, 0.0) if not missing else 0.0
    cdh = max(t - spec.cooling_threshold_c, 0.0) if not missing else 0.0
    rh = 0.0 if math.isnan(humidity) else humidity / 100.0
    angle = 2.0 * math.pi * local_hour / 24.0
    return [
        t,
        hdh,
        cdh,
        rh,
        cdh * math.sin(angle),
        cdh * math.cos(angle),
        hdh * math.sin(angle),
        hdh * math.cos(angle),
        float(missing),
    ]


@dataclass(frozen=True)
class Design:
    """Feature rows for many (origin, horizon) pairs of one authority."""

    x: np.ndarray
    """Rows by features."""
    scale: np.ndarray
    """The scale per row (mean of the week ending at the origin, MW)."""
    target_position: np.ndarray
    origin_position: np.ndarray
    horizon: np.ndarray
    usable: np.ndarray
    """False where the origin had no scale; those rows carry no forecast."""
    local_hour: np.ndarray


def design(
    series: SeriesIndex,
    origin_positions: np.ndarray,
    horizons: np.ndarray,
    offsets: np.ndarray,
    temperature: np.ndarray,
    humidity: np.ndarray,
    spec: FeatureSpec,
) -> Design:
    """Every (origin, horizon) row at once. ``offsets``, ``temperature`` and ``humidity`` are
    aligned with the series positions. Lags are checked against the horizon before any read."""
    y = series.values
    n = len(y)
    o = np.repeat(origin_positions.astype(np.int64), len(horizons))
    h = np.tile(horizons.astype(np.int64), len(origin_positions))
    t = o + h
    same = 24 * np.ceil(h / 24).astype(np.int64)
    for lag_array in (same, same + 24, np.full_like(h, SEASONAL_LAG), np.full_like(h, 2 * SEASONAL_LAG), h):
        if np.any(lag_array < h):
            raise LeakageError("a target relative lag reaches past the origin")

    def read(position: np.ndarray) -> np.ndarray:
        out = np.full(len(position), np.nan)
        ok = (position >= 0) & (position < n)
        out[ok] = y[position[ok]]
        return out

    # Means of the last week and the last day ending at the origin, per distinct origin.
    cumsum = np.concatenate([[0.0], np.nancumsum(y)])
    counts = np.concatenate([[0], np.cumsum(np.isfinite(y).astype(np.int64))])

    def window_mean(end_positions: np.ndarray, hours: int) -> np.ndarray:
        stop = np.clip(end_positions + 1, 0, n)
        start = np.clip(stop - hours, 0, n)
        total = cumsum[stop] - cumsum[start]
        count = counts[stop] - counts[start]
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(count > 0, total / np.maximum(count, 1), np.nan)

    scale_by_origin = window_mean(origin_positions.astype(np.int64), SEASONAL_LAG)
    mean24_by_origin = window_mean(origin_positions.astype(np.int64), 24)
    scale = np.repeat(scale_by_origin, len(horizons))
    mean24 = np.repeat(mean24_by_origin, len(horizons))
    usable = np.isfinite(scale) & (scale > 0)
    safe_scale = np.where(usable, scale, 1.0)

    r_same = read(t - same) / safe_scale
    r_same_prev = read(t - same - 24) / safe_scale
    r_week = read(t - SEASONAL_LAG) / safe_scale
    r_two = read(t - 2 * SEASONAL_LAG) / safe_scale
    r_origin = read(o) / safe_scale
    r_mean24 = mean24 / safe_scale
    fallback = np.where(np.isfinite(r_mean24), r_mean24, 1.0)

    def filled(values: np.ndarray) -> np.ndarray:
        return np.where(np.isfinite(values), values, fallback)

    offset_t = offsets[np.clip(t, 0, n - 1)] if len(offsets) == n else np.repeat(offsets, len(t))
    # Calendar per target hour, computed once per distinct (target, offset) pair.
    keys = np.stack([t, offset_t], axis=1)
    unique, inverse = np.unique(keys, axis=0, return_inverse=True)
    cal_rows = np.empty((len(unique), 6), dtype=np.float64)
    for i, (position, offset) in enumerate(unique):
        target_utc = series.hour_at(int(position))
        cal = calendar_at(target_utc, int(offset), spec.country)
        cal_rows[i] = [
            cal.local_hour,
            cal.local_day.weekday(),
            cal.weekend,
            cal.holiday,
            cal.day_of_year,
            0.0,
        ]
    cal_rows = cal_rows[inverse.ravel()]
    local_hour = cal_rows[:, 0]
    weekday = cal_rows[:, 1]
    columns: list[np.ndarray] = [
        np.ones(len(t)),
        filled(r_same),
        filled(r_same_prev),
        filled(r_week),
        filled(r_two),
        filled(r_origin),
        fallback,
        (~np.isfinite(r_same)).astype(np.float64),
        (~np.isfinite(r_week)).astype(np.float64),
        (h > 24).astype(np.float64),
        h / 48.0,
        cal_rows[:, 2],
        cal_rows[:, 3],
    ]
    for k in range(1, spec.fourier_daily + 1):
        angle = 2.0 * np.pi * k * local_hour / 24.0
        columns += [np.sin(angle), np.cos(angle)]
    for k in range(1, spec.fourier_weekly + 1):
        angle = 2.0 * np.pi * k * (weekday * 24 + local_hour) / 168.0
        columns += [np.sin(angle), np.cos(angle)]
    for k in range(1, spec.fourier_yearly + 1):
        angle = 2.0 * np.pi * k * cal_rows[:, 4] / 365.25
        columns += [np.sin(angle), np.cos(angle)]
    if spec.use_weather:
        columns += list(weather_block(t, n, local_hour, temperature, humidity, spec).T)
    x = np.stack(columns, axis=1)
    assert x.shape[1] == len(feature_names(spec))
    return Design(
        x=x,
        scale=scale,
        target_position=t,
        origin_position=o,
        horizon=h,
        usable=usable,
        local_hour=local_hour,
    )


WEATHER_COLUMNS = 9


def weather_block(
    t: np.ndarray,
    n: int,
    local_hour: np.ndarray,
    temperature: np.ndarray,
    humidity: np.ndarray,
    spec: FeatureSpec,
) -> np.ndarray:
    """The nine observed weather columns for target positions ``t``; the only columns a threshold changes."""
    temp = temperature[np.clip(t, 0, n - 1)].astype(np.float64)
    temp = np.where((t >= 0) & (t < n), temp, np.nan)
    rh = humidity[np.clip(t, 0, n - 1)].astype(np.float64)
    rh = np.where((t >= 0) & (t < n), rh, np.nan)
    missing = ~np.isfinite(temp)
    tt = np.where(missing, 0.0, temp)
    hdh = np.where(missing, 0.0, np.maximum(spec.heating_threshold_c - tt, 0.0))
    cdh = np.where(missing, 0.0, np.maximum(tt - spec.cooling_threshold_c, 0.0))
    rhh = np.where(np.isfinite(rh), rh / 100.0, 0.0)
    angle = 2.0 * np.pi * local_hour / 24.0
    return np.stack(
        [
            tt,
            hdh,
            cdh,
            rhh,
            cdh * np.sin(angle),
            cdh * np.cos(angle),
            hdh * np.sin(angle),
            hdh * np.cos(angle),
            missing.astype(np.float64),
        ],
        axis=1,
    )


def with_thresholds(
    d: Design, temperature: np.ndarray, humidity: np.ndarray, n: int, spec: FeatureSpec
) -> Design:
    """The same design with the weather block rebuilt for other thresholds."""
    if not spec.use_weather:
        return d
    x = d.x.copy()
    x[:, -WEATHER_COLUMNS:] = weather_block(d.target_position, n, d.local_hour, temperature, humidity, spec)
    return Design(
        x=x,
        scale=d.scale,
        target_position=d.target_position,
        origin_position=d.origin_position,
        horizon=d.horizon,
        usable=d.usable,
        local_hour=d.local_hour,
    )
