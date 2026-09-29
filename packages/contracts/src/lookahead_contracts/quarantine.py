"""Quarantine rules for the hourly demand panel. Named, counted, nothing deleted.

Every rule marks rows; the clean demand column is null where any rule fired, the raw
value stays in ``demand_raw``, and the report counts each rule per authority. A missing
hour is inserted as a null row and flagged, so the panel is a complete hourly grid per
authority from its first hour to its last.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl
from lookahead_core.config import POLICY

RULES: tuple[str, ...] = (
    "demand_missing",
    "demand_nonpositive",
    "demand_spike",
    "duplicate_hour",
    "missing_hour",
    "forecast_missing",
    "revision",
)


class QuarantineError(ValueError):
    pass


@dataclass(frozen=True)
class Quarantined:
    panel: pl.DataFrame
    report: pl.DataFrame
    revisions: int


def _require(frame: pl.DataFrame, columns: tuple[str, ...]) -> None:
    if frame.height == 0:
        raise QuarantineError("the quarantine was handed an empty frame")
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise QuarantineError(f"the quarantine needs the columns {missing}")


def resolve_revisions(balance: pl.DataFrame) -> tuple[pl.DataFrame, pl.DataFrame, int]:
    """Where two files carry the same authority and hour, keep the later file's row.

    Returns the resolved frame, the duplicate rows within one file (a separate defect), and
    the count of hours whose demand changed between files.
    """
    _require(balance, ("authority", "utc_hour", "demand", "source_file"))
    ordered = balance.with_row_index("row").sort(["authority", "utc_hour", "source_file", "row"])
    # Duplicates inside one file: the same authority and hour twice with the same source.
    within = ordered.filter(pl.struct(["authority", "utc_hour", "source_file"]).is_duplicated())
    dedup_within = ordered.unique(
        subset=["authority", "utc_hour", "source_file"], keep="last", maintain_order=True
    )
    # Across files: the later file (sorted last by name, which orders the half years) wins.
    counts = dedup_within.group_by(["authority", "utc_hour"]).agg(
        pl.len().alias("copies"),
        pl.col("demand").n_unique().alias("distinct_demand"),
    )
    revised = counts.filter((pl.col("copies") > 1) & (pl.col("distinct_demand") > 1)).height
    resolved = dedup_within.unique(subset=["authority", "utc_hour"], keep="last", maintain_order=True).drop(
        "row"
    )
    return resolved, within.drop("row"), revised


def complete_grid(frame: pl.DataFrame) -> pl.DataFrame:
    """One row per authority per hour from its first to its last hour; inserted hours are flagged."""
    _require(frame, ("authority", "utc_hour"))
    spans = frame.group_by("authority").agg(
        pl.col("utc_hour").min().alias("start"), pl.col("utc_hour").max().alias("end")
    )
    grids = []
    for row in spans.sort("authority").iter_rows(named=True):
        hours = pl.datetime_range(row["start"], row["end"], interval="1h", time_zone="UTC", eager=True)
        grids.append(pl.DataFrame({"authority": [row["authority"]] * len(hours), "utc_hour": hours}))
    grid = pl.concat(grids)
    joined = grid.join(
        frame.with_columns(pl.lit(False).alias("missing_hour")), on=["authority", "utc_hour"], how="left"
    )
    return joined.with_columns(pl.col("missing_hour").fill_null(True)).sort(["authority", "utc_hour"])


def apply_rules(balance: pl.DataFrame) -> Quarantined:
    """Run every rule, in order, over the concatenated balance frame."""
    _require(balance, ("authority", "utc_hour", "demand", "forecast_operator", "source_file"))
    # A NaN is a missing value, not the largest number: it is made null before any rule compares it.
    balance = balance.with_columns(
        pl.col("demand").cast(pl.Float64).fill_nan(None),
        pl.col("forecast_operator").cast(pl.Float64).fill_nan(None),
    )
    resolved, within, revisions = resolve_revisions(balance)
    duplicated_keys = (
        within.select("authority", "utc_hour").unique().with_columns(pl.lit(True).alias("duplicate_hour"))
    )
    panel = complete_grid(resolved).join(duplicated_keys, on=["authority", "utc_hour"], how="left")
    if "utc_offset_hours" in panel.columns:
        panel = panel.with_columns(
            pl.col("utc_offset_hours")
            .fill_null(strategy="forward")
            .fill_null(strategy="backward")
            .over("authority")
        )
    window = POLICY.rolling_median_days * 24
    panel = (
        panel.with_columns(pl.col("duplicate_hour").fill_null(False))
        .with_columns(pl.col("demand").alias("demand_raw"))
        .with_columns(
            pl.col("demand_raw")
            .rolling_median(window_size=window, min_samples=24 * 7)
            .shift(1)
            .over("authority")
            .alias("rolling_median")
        )
        .with_columns(
            (pl.col("demand_raw").is_null() & ~pl.col("missing_hour")).alias("demand_missing"),
            (pl.col("demand_raw") <= 0).fill_null(False).alias("demand_nonpositive"),
            (
                (pl.col("demand_raw") > POLICY.spike_multiple_of_rolling_median * pl.col("rolling_median"))
                & (pl.col("demand_raw") > 0)
            )
            .fill_null(False)
            .alias("demand_spike"),
            (pl.col("forecast_operator").is_null() & ~pl.col("missing_hour")).alias("forecast_missing"),
        )
    )
    flagged = pl.any_horizontal(
        pl.col("demand_missing"),
        pl.col("demand_nonpositive"),
        pl.col("demand_spike"),
        pl.col("duplicate_hour"),
        pl.col("missing_hour"),
    )
    panel = panel.with_columns(
        pl.when(flagged).then(None).otherwise(pl.col("demand_raw")).alias("demand"),
        flagged.alias("quarantined"),
    ).drop("rolling_median")
    report = (
        panel.group_by("authority")
        .agg(
            pl.len().alias("hours"),
            *[pl.col(rule).sum().alias(rule) for rule in RULES if rule != "revision"],
            pl.col("quarantined").sum().alias("quarantined"),
        )
        .with_columns(pl.lit(0).alias("revision"))
        .sort("authority")
    )
    return Quarantined(panel=panel, report=report, revisions=revisions)


def check_report_matches_panel(panel: pl.DataFrame, report: pl.DataFrame) -> None:
    """The counts in the report equal the flags in the panel, rule by rule."""
    for rule in RULES:
        if rule == "revision":
            continue
        from_panel = int(panel[rule].sum())
        from_report = int(report[rule].sum())
        if from_panel != from_report:
            raise QuarantineError(
                f"rule {rule}: {from_panel} flagged rows in the panel, {from_report} in the report"
            )
