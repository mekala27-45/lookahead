"""Small typed helpers over polars, so the stages read as arithmetic rather than casts."""

from __future__ import annotations

from datetime import UTC, date, datetime

import polars as pl


def mean(frame: pl.DataFrame, column: str) -> float:
    value = frame[column].mean()
    if not isinstance(value, int | float):
        raise TypeError(f"{column} has no numeric mean")
    return float(value)


def total(frame: pl.DataFrame, column: str) -> float:
    value = frame[column].sum()
    if not isinstance(value, int | float):
        raise TypeError(f"{column} has no numeric sum")
    return float(value)


def share(frame: pl.DataFrame, predicate: pl.Expr) -> float:
    if frame.height == 0:
        raise ValueError("share of an empty frame")
    return frame.filter(predicate).height / frame.height


def median(frame: pl.DataFrame, column: str) -> float:
    value = frame[column].median()
    if not isinstance(value, int | float):
        raise TypeError(f"{column} has no numeric median")
    return float(value)


def as_datetime(value: object) -> datetime:
    """A polars scalar that has to be a datetime, typed as one."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    raise TypeError(f"expected a datetime, got {type(value).__name__}")


def as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"expected a date, got {type(value).__name__}")


def as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, got {type(value).__name__}")
    return float(value)


def as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"expected a number, got {type(value).__name__}")
    return int(value)
