"""Small typed helpers over polars, so the stages read as arithmetic rather than casts."""

from __future__ import annotations

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
