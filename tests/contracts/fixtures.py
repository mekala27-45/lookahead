"""Small EIA-930 shaped files for the tests: the real column names, thousands separators in
quotes, the timestamp formats EIA has used, and defects planted at stated rows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

BALANCE_HEADER = (
    "Balancing Authority,Data Date,Hour Number,Local Time at End of Hour,UTC Time at End of Hour,"
    "Demand Forecast (MW),Demand (MW),Net Generation (MW),Total Interchange (MW),Region"
)
SUBREGION_HEADER = "Balancing Authority,Sub-Region,Data Date,Hour Number,Local Time at End of Hour,UTC Time at End of Hour,Demand (MW)"


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f'"{int(round(value)):,}"'


def write_balance(
    path: Path,
    authorities: dict[str, str],
    start: datetime,
    hours: int,
    *,
    seed: int = 1,
    defects: dict[tuple[str, int], str] | None = None,
    time_format: str = "%m/%d/%Y %I:%M:%S %p",
    generation_only: tuple[str, ...] = (),
    bases: dict[str, float] | None = None,
) -> Path:
    """Hourly rows for each authority. ``defects`` maps (authority, hour index) to a defect kind:
    missing, zero, negative, spike, duplicate, skip, forecast_missing."""
    rng = np.random.default_rng(seed)
    defects = defects or {}
    lines = [BALANCE_HEADER]
    for authority, region in authorities.items():
        base = (bases or {}).get(authority, 10_000.0 + rng.uniform(0, 5_000))
        for i in range(hours):
            kind = defects.get((authority, i))
            if kind == "skip":
                continue
            stamp = start + timedelta(hours=i + 1)
            demand: float | None = base * (1 + 0.2 * np.sin(2 * np.pi * (i % 24) / 24)) + (
                0.0 if bases and authority in bases else rng.normal(0, 100)
            )
            forecast: float | None = demand + rng.normal(0, 200) if demand is not None else None
            if authority in generation_only:
                demand, forecast = None, None
            if kind == "missing":
                demand = None
            elif kind == "zero":
                demand = 0.0
            elif kind == "negative":
                demand = -500.0
            elif kind == "spike":
                demand = base * 12.0
            elif kind == "forecast_missing":
                forecast = None
            elif kind == "forecast_negative":
                forecast = -40.0
            local = stamp - timedelta(hours=5)
            row = (
                f"{authority},{local:%m/%d/%Y},{(i % 24) + 1},{local.strftime(time_format)},{stamp.strftime(time_format)},"
                f"{_fmt(forecast)},{_fmt(demand)},{_fmt(base)},{_fmt(0)},{region}"
            )
            lines.append(row)
            if kind == "duplicate":
                lines.append(row)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_subregion(path: Path, parts: dict[str, dict[str, float]], start: datetime, hours: int) -> Path:
    """``parts`` maps authority to {subregion: share of a 10,000 MW authority}."""
    lines = [SUBREGION_HEADER]
    for authority, shares in parts.items():
        for sub, share in shares.items():
            for i in range(hours):
                stamp = start + timedelta(hours=i + 1)
                local = stamp - timedelta(hours=5)
                demand = 10_000.0 * share * (1 + 0.2 * np.sin(2 * np.pi * (i % 24) / 24))
                lines.append(
                    f"{authority},{sub},{local:%m/%d/%Y},{(i % 24) + 1},{local:%m/%d/%Y %I:%M:%S %p},"
                    f"{stamp:%m/%d/%Y %I:%M:%S %p},{_fmt(demand)}"
                )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def utc(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=UTC)
