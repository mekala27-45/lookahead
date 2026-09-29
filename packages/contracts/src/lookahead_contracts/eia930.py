"""EIA-930, the Hourly Electric Grid Monitor, read from the six month files.

The balance files carry, per balancing authority and UTC hour ending, the demand, the
operator's day ahead demand forecast, net generation and total interchange, plus EIA's
region assignment. The subregion files carry demand for the subregions of eight
authorities. Numbers arrive as strings with thousands separators; timestamps have changed
format across the years, so both are parsed here and nowhere else.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import polars as pl

BALANCE_COLUMNS = {
    "Balancing Authority": "authority",
    "Local Time at End of Hour": "local_hour_text",
    "UTC Time at End of Hour": "utc_hour_text",
    "Demand Forecast (MW)": "forecast_operator",
    "Demand (MW)": "demand",
    "Net Generation (MW)": "net_generation",
    "Total Interchange (MW)": "interchange",
    "Region": "region",
}

SUBREGION_COLUMNS = {
    "Balancing Authority": "authority",
    "Sub-Region": "subregion",
    "UTC Time at End of Hour": "utc_hour_text",
    "Demand (MW)": "demand",
}

NUMERIC = ("forecast_operator", "demand", "net_generation", "interchange")

FILE_PATTERN = re.compile(r"EIA930_(BALANCE|SUBREGION)_(\d{4})_(Jan_Jun|Jul_Dec)\.csv(\.gz)?$")

# The formats EIA has used for the UTC hour ending column, tried in order.
TIME_FORMATS = (
    "%m/%d/%Y %I:%M:%S %p",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)


@dataclass(frozen=True)
class SixMonthFile:
    path: Path
    kind: str
    year: int
    half: str

    @property
    def order(self) -> tuple[int, int]:
        return (self.year, 0 if self.half == "Jan_Jun" else 1)

    @property
    def label(self) -> str:
        return f"{self.year}_{self.half}"


def discover_files(folder: Path) -> list[SixMonthFile]:
    """Every six month file in the folder, ordered by half year; gzip copies count as the file."""
    found: dict[tuple[str, str], SixMonthFile] = {}
    for path in sorted(folder.glob("EIA930_*")):
        match = FILE_PATTERN.search(path.name)
        if match is None:
            continue
        kind, year, half, _ = match.groups()
        key = (kind, f"{year}_{half}")
        candidate = SixMonthFile(path=path, kind=kind, year=int(year), half=half)
        # Prefer the plain csv when both a csv and a csv.gz of the same half exist.
        if key not in found or path.suffix == ".csv":
            found[key] = candidate
    return sorted(found.values(), key=lambda f: (f.kind, f.order))


def expected_halves(first: str, last: str) -> list[str]:
    """Half year labels from first to last inclusive, for the completeness check."""

    def order(label: str) -> tuple[int, int]:
        return (int(label[:4]), 0 if label[5:] == "Jan_Jun" else 1)

    out: list[str] = []
    year, half = order(first)
    while (year, half) <= order(last):
        out.append(f"{year}_{'Jan_Jun' if half == 0 else 'Jul_Dec'}")
        year, half = (year, 1) if half == 0 else (year + 1, 0)
    return out


def _parse_time(column: pl.Expr) -> pl.Expr:
    """Try each known timestamp format; the first that parses a value wins for that value."""
    expr: pl.Expr | None = None
    for fmt in TIME_FORMATS:
        parsed = column.str.strptime(pl.Datetime("us"), fmt, strict=False)
        expr = parsed if expr is None else expr.fill_null(parsed)
    assert expr is not None
    return expr.dt.replace_time_zone("UTC")


def _to_number(column: pl.Expr) -> pl.Expr:
    cleaned = column.str.strip_chars().str.replace_all(",", "").str.replace_all('"', "")
    return (
        pl.when(cleaned.is_in(["", "NA", "N/A", "null", "NULL", "-"]))
        .then(None)
        .otherwise(cleaned)
        .cast(pl.Float64, strict=False)
    )


def read_balance(path: Path) -> pl.DataFrame:
    """One balance file as a typed frame: authority, utc_hour, the four series, region, source."""
    raw = pl.read_csv(path, infer_schema_length=0, encoding="utf8-lossy", truncate_ragged_lines=True)
    missing = [c for c in BALANCE_COLUMNS if c not in raw.columns and c != "Region"]
    if missing:
        raise ValueError(f"{path.name} lacks the columns {missing}")
    if "Region" not in raw.columns:
        raw = raw.with_columns(pl.lit(None, dtype=pl.Utf8).alias("Region"))
    frame = raw.select([pl.col(src).alias(dst) for src, dst in BALANCE_COLUMNS.items()])
    frame = frame.with_columns(
        _parse_time(pl.col("utc_hour_text")).alias("utc_hour"),
        _parse_time(pl.col("local_hour_text")).dt.replace_time_zone(None).alias("local_hour"),
        *[_to_number(pl.col(c)).alias(c) for c in NUMERIC],
        pl.col("authority").str.strip_chars(),
        pl.col("region").str.strip_chars(),
        pl.lit(path.name).alias("source_file"),
    )
    unparsed = frame.filter(pl.col("utc_hour").is_null()).height
    if unparsed:
        sample = frame.filter(pl.col("utc_hour").is_null())["utc_hour_text"].head(3).to_list()
        raise ValueError(f"{path.name}: {unparsed} timestamps did not parse, for example {sample}")
    # The local offset, in whole hours, from the two clocks EIA prints side by side.
    frame = frame.with_columns(
        ((pl.col("local_hour") - pl.col("utc_hour").dt.replace_time_zone(None)).dt.total_minutes() / 60)
        .round(0)
        .cast(pl.Int8)
        .alias("utc_offset_hours")
    )
    return frame.drop("utc_hour_text", "local_hour_text", "local_hour").select(
        "authority",
        "utc_hour",
        "utc_offset_hours",
        "demand",
        "forecast_operator",
        "net_generation",
        "interchange",
        "region",
        "source_file",
    )


def read_subregion(path: Path) -> pl.DataFrame:
    raw = pl.read_csv(path, infer_schema_length=0, encoding="utf8-lossy", truncate_ragged_lines=True)
    missing = [c for c in SUBREGION_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError(f"{path.name} lacks the columns {missing}")
    frame = raw.select([pl.col(src).alias(dst) for src, dst in SUBREGION_COLUMNS.items()])
    frame = frame.with_columns(
        _parse_time(pl.col("utc_hour_text")).alias("utc_hour"),
        _to_number(pl.col("demand")).alias("demand"),
        pl.col("authority").str.strip_chars(),
        pl.col("subregion").str.strip_chars(),
        pl.lit(path.name).alias("source_file"),
    )
    unparsed = frame.filter(pl.col("utc_hour").is_null()).height
    if unparsed:
        raise ValueError(f"{path.name}: {unparsed} subregion timestamps did not parse")
    return frame.drop("utc_hour_text").select("authority", "subregion", "utc_hour", "demand", "source_file")


def concat_in_order(frames: Iterable[pl.DataFrame]) -> pl.DataFrame:
    frames = list(frames)
    if not frames:
        raise ValueError("no frames to concatenate")
    return pl.concat(frames, how="vertical_relaxed")


def region_of_authorities(balance: pl.DataFrame) -> pl.DataFrame:
    """Each authority's region as EIA assigns it; the most recent non null assignment wins."""
    ranked = (
        balance.filter(pl.col("region").is_not_null() & (pl.col("region") != ""))
        .sort(["authority", "utc_hour"])
        .group_by("authority", maintain_order=True)
        .agg(pl.col("region").last().alias("region"))
    )
    return ranked.sort("authority")


def demand_reporters(balance: pl.DataFrame, minimum_share: float = 0.5) -> pl.DataFrame:
    """Which authorities report demand: those with a non null demand in at least half of the hours
    between their first and last reported demand.

    Generation only authorities report net generation and interchange and no demand; they are
    listed with their share so the README can print the rule and the count. An authority that
    started reporting late (or stopped early) is judged over its own span, not the files' span.
    """
    with_demand = balance.filter(pl.col("demand").is_not_null() & pl.col("demand").is_not_nan())
    spans = with_demand.group_by("authority").agg(
        pl.col("utc_hour").min().alias("first_demand_hour"),
        pl.col("utc_hour").max().alias("last_demand_hour"),
        pl.len().alias("hours_with_demand"),
    )
    totals = balance.group_by("authority").agg(
        pl.len().alias("hours"),
        pl.col("utc_hour").min().alias("first_hour"),
        pl.col("utc_hour").max().alias("last_hour"),
    )
    joined = totals.join(spans, on="authority", how="left")
    span_hours = ((pl.col("last_demand_hour") - pl.col("first_demand_hour")).dt.total_hours() + 1).cast(
        pl.Float64
    )
    return (
        joined.with_columns(
            pl.col("hours_with_demand").fill_null(0),
            (pl.col("hours_with_demand").fill_null(0) / span_hours).fill_null(0.0).alias("demand_share"),
        )
        .with_columns((pl.col("demand_share") >= minimum_share).alias("reports_demand"))
        .sort("authority")
    )


def check_halves_complete(files: Sequence[SixMonthFile], kind: str, first: str) -> list[str]:
    """Half years missing between the first expected and the latest present, for the provenance note."""
    present = {f.label for f in files if f.kind == kind}
    if not present:
        return [first]
    latest = max((f for f in files if f.kind == kind), key=lambda f: f.order).label
    return [h for h in expected_halves(first, latest) if h not in present]
