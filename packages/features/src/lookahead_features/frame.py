"""The point in time frame: what a forecaster can see at an origin, and nothing after it.

A ``SeriesIndex`` holds one authority's hourly series as a contiguous array from a stated
first hour. A ``PointInTimeFrame`` wraps it with an origin and exposes only the values at
or before that origin: ``history`` slices end at the origin, ``at`` raises for any later
hour, and ``before`` can only move the origin earlier. Feature code receives the frame, not
the series, so a lag that reaches past the origin is a raised error rather than a leak.
Ported in spirit from pricepoint's weekly frame; the enforcement is the same.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

HOUR = timedelta(hours=1)


class LeakageError(ValueError):
    """A read at or after the frame's boundary."""


@dataclass(frozen=True)
class SeriesIndex:
    authority: str
    first_hour: datetime
    values: np.ndarray
    """Demand in megawatts, hour ending; NaN where quarantined or missing."""

    @property
    def last_hour(self) -> datetime:
        return self.first_hour + HOUR * (len(self.values) - 1)

    def position(self, hour: datetime) -> int:
        delta = hour - self.first_hour
        seconds = delta.total_seconds()
        if seconds % 3600:
            raise ValueError(f"{hour} is not on the hour")
        return int(seconds // 3600)

    def hour_at(self, position: int) -> datetime:
        return self.first_hour + HOUR * position

    @classmethod
    def from_panel(cls, panel: pl.DataFrame, authority: str, column: str = "demand") -> SeriesIndex:
        rows = panel.filter(pl.col("authority") == authority).sort("utc_hour")
        if rows.height == 0:
            raise ValueError(f"no rows for {authority}")
        hours = rows["utc_hour"]
        first = hours[0]
        if not isinstance(first, datetime):
            raise TypeError("utc_hour has to be a datetime column")
        if first.tzinfo is None:
            first = first.replace(tzinfo=UTC)
        expected = rows.height
        last = hours[rows.height - 1]
        if not isinstance(last, datetime):
            raise TypeError("utc_hour has to be a datetime column")
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        span = int((last - first).total_seconds() // 3600) + 1
        if span != expected:
            raise ValueError(
                f"{authority}: {expected} rows over {span} hours; the panel is not a complete grid"
            )
        values = rows[column].cast(pl.Float64).fill_null(float("nan")).to_numpy().astype(np.float64)
        return cls(authority=authority, first_hour=first, values=values)


class PointInTimeFrame:
    """One authority's history up to and including the origin. Nothing after it can be read."""

    def __init__(self, series: SeriesIndex, origin: datetime) -> None:
        if origin.tzinfo is None:
            raise ValueError("the origin has to carry a time zone")
        if origin < series.first_hour:
            raise ValueError("the origin is before the series starts")
        self.series = series
        self.origin = origin
        self.__end = min(series.position(origin), len(series.values) - 1) + 1
        # The array is sliced once, at construction, so no method can reach past it.
        self.__visible = series.values[: self.__end]

    @property
    def authority(self) -> str:
        return self.series.authority

    @property
    def visible_hours(self) -> int:
        return self.__end

    def history(self, hours: int) -> np.ndarray:
        """The last ``hours`` values ending at the origin, NaN padded at the front when short."""
        if hours <= 0:
            raise ValueError("history needs a positive length")
        window = self.__visible[max(0, self.__end - hours) : self.__end]
        if len(window) < hours:
            window = np.concatenate([np.full(hours - len(window), np.nan), window])
        return window

    def at(self, hour: datetime) -> float:
        """The value at a past hour; raises for any hour after the origin."""
        if hour > self.origin:
            raise LeakageError(f"{hour} is after the origin {self.origin}")
        position = self.series.position(hour)
        if position < 0 or position >= self.__end:
            return float("nan")
        return float(self.__visible[position])

    def lag(self, target: datetime, hours_back: int) -> float:
        """The value ``hours_back`` before ``target``; raises when that hour is after the origin."""
        when = target - HOUR * hours_back
        return self.at(when)

    def before(self, cutoff: datetime) -> PointInTimeFrame:
        if cutoff > self.origin:
            raise LeakageError("a point in time frame cannot extend its origin")
        return PointInTimeFrame(self.series, cutoff)

    def collect(self) -> np.ndarray:
        return self.__visible.copy()
