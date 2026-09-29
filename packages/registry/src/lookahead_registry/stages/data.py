"""Stage: EIA-930 in full, the quarantine, the hierarchy and the London release.

Reads the six month files under data/external/eia930 and the London release under
data/external/london. Writes:

  data/eia930/hourly.parquet        the hourly panel of every demand reporting authority, quarantined
  data/eia930/subregions.parquet    subregion demand for the eight authorities that publish it
  data/eia930/quarantine.parquet    the quarantine report per authority and rule
  data/eia930/authorities.csv       every authority in the files with its region and the demand rule
  data/eia930/windows.json          the training, validation and test windows every stage uses
  data/hierarchy.csv                the lower 48, interconnections, regions, authorities, subregions
  data/london/checks.json           row, household and defect counts of the raw release
  results/manifests/data.json       every figure the documents quote about the data
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
from lookahead_contracts import eia930, london, quarantine
from lookahead_contracts.hierarchy_table import build_hierarchy
from lookahead_core.config import POLICY
from lookahead_core.frames import as_date, as_datetime, as_float
from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths

FIRST_HALF = "2018_Jul_Dec"
"""The first half year with subregion demand; the balance files start earlier but the build reads the same window."""

COMPLETE_DAY_SHARE = 0.9
"""A UTC day is complete when this share of demand reporting authorities has demand in all 24 hours."""


class DataMissing(RuntimeError):
    pass


def run(paths: Paths, as_of: str, seed: int, *, require_london: bool = True) -> Manifest:
    files = eia930.discover_files(paths.external_eia)
    balance_files = [f for f in files if f.kind == "BALANCE"]
    subregion_files = [f for f in files if f.kind == "SUBREGION"]
    if not balance_files:
        raise DataMissing(
            f"no EIA930_BALANCE files under {paths.external_eia}; expected EIA930_BALANCE_<year>_<Jan_Jun|Jul_Dec>.csv "
            f"from {FIRST_HALF} onward (see data/PROVENANCE.md)"
        )
    missing_halves = eia930.check_halves_complete(files, "BALANCE", FIRST_HALF)
    if missing_halves:
        raise DataMissing(f"balance files missing for the half years {missing_halves}")
    manifest = Manifest(as_of=as_of, seed=seed)
    w = Scribe(
        manifest,
        source="real:eia930",
        population="every six month file from 2018_Jul_Dec",
        origin="lookahead_registry.stages.data",
    )

    balance = eia930.concat_in_order(eia930.read_balance(f.path) for f in balance_files)
    subregions_raw = (
        eia930.concat_in_order(eia930.read_subregion(f.path) for f in subregion_files)
        if subregion_files
        else None
    )
    reporters = eia930.demand_reporters(balance)
    regions = eia930.region_of_authorities(balance)
    authorities = reporters.join(regions, on="authority", how="left")
    demand_authorities = authorities.filter(pl.col("reports_demand"))["authority"].to_list()
    unassigned = authorities.filter(pl.col("region").is_null() & pl.col("reports_demand"))[
        "authority"
    ].to_list()
    if unassigned:
        raise DataMissing(f"demand reporting authorities without a region in the files: {unassigned}")

    quarantined = quarantine.apply_rules(balance.filter(pl.col("authority").is_in(demand_authorities)))
    quarantine.check_report_matches_panel(quarantined.panel, quarantined.report)
    panel = quarantined.panel.with_columns(pl.col("authority").cast(pl.Utf8)).join(
        regions, on="authority", how="left", suffix="_assigned"
    )
    panel = panel.drop("region").rename({"region_assigned": "region"})

    hierarchy_regions = authorities.filter(pl.col("reports_demand")).select("authority", "region")
    subregions = None
    if subregions_raw is not None:
        subregions = (
            subregions_raw.filter(pl.col("authority").is_in(demand_authorities))
            .unique(subset=["authority", "subregion", "utc_hour"], keep="last")
            .sort(["authority", "subregion", "utc_hour"])
        )
    hierarchy = build_hierarchy(hierarchy_regions, subregions)

    windows = _windows(panel, demand_authorities)
    authorities = authorities.join(_eligibility(panel, windows), on="authority", how="left").with_columns(
        pl.col("validation_coverage").fill_null(0.0),
        pl.col("test_coverage").fill_null(0.0),
        pl.col("backtest_eligible").fill_null(False),
    )
    gap = _subregion_gap(panel, subregions) if subregions is not None else None

    paths.eia.mkdir(parents=True, exist_ok=True)
    # EIA reports whole megawatts; storing them as 32 bit integers halves the committed file.
    megawatts = ["demand", "demand_raw", "forecast_operator", "net_generation", "interchange"]
    panel = panel.with_columns([pl.col(c).round(0).cast(pl.Int32) for c in megawatts]).drop("source_file")
    # The clean demand is the raw demand with the quarantined hours nulled; load_panel rebuilds it.
    panel.drop("demand").write_parquet(paths.eia / "hourly.parquet", compression="zstd", compression_level=9)
    quarantined.report.write_parquet(paths.eia / "quarantine.parquet")
    if subregions is not None:
        subregions = subregions.with_columns(pl.col("demand").round(0).cast(pl.Int32)).drop("source_file")
        subregions.write_parquet(paths.eia / "subregions.parquet", compression="zstd", compression_level=9)
    authorities.with_columns(
        pl.col("first_hour").dt.strftime("%Y-%m-%dT%H:%MZ"),
        pl.col("last_hour").dt.strftime("%Y-%m-%dT%H:%MZ"),
    ).write_csv(paths.eia / "authorities.csv")
    hierarchy.write_csv(paths.data / "hierarchy.csv")
    (paths.eia / "windows.json").write_text(json.dumps(windows, indent=1) + "\n", encoding="utf-8")
    if gap is not None:
        gap.write_parquet(paths.eia / "subregion_gap.parquet")

    _eia_figures(
        w,
        manifest,
        balance_files,
        subregion_files,
        authorities,
        quarantined,
        panel,
        subregions,
        hierarchy,
        windows,
        gap,
    )
    _london(paths, manifest, require_london)
    out = paths.results / "manifests" / "data.json"
    manifest.save(out)
    return manifest


def _windows(panel: pl.DataFrame, demand_authorities: list[str]) -> dict[str, str | int]:
    """The last complete UTC day closes the test year; the twelve months before it are validation."""
    days = (
        panel.with_columns((pl.col("utc_hour") - pl.duration(hours=1)).dt.date().alias("day"))
        .group_by(["day", "authority"])
        .agg(pl.col("demand").is_not_null().sum().alias("hours_with_demand"))
        .group_by("day")
        .agg((pl.col("hours_with_demand") == 24).sum().alias("complete_authorities"))
        .sort("day")
    )
    threshold = COMPLETE_DAY_SHARE * len(demand_authorities)
    complete = days.filter(pl.col("complete_authorities") >= threshold)["day"]
    if complete.is_empty():
        raise DataMissing("no complete UTC day in the panel")
    end = as_date(complete.max())
    test_start = end - timedelta(days=365) + timedelta(days=1)
    validation_start = test_start - timedelta(days=365)
    first = as_datetime(panel["utc_hour"].min())
    return {
        "training_start": (first - timedelta(hours=1)).date().isoformat(),
        "validation_start": validation_start.isoformat(),
        "test_start": test_start.isoformat(),
        "test_end": end.isoformat(),
        "test_days": 365,
        "validation_days": 365,
    }


MINIMUM_WINDOW_COVERAGE = 0.9
"""An authority is in the backtest when its clean demand covers this share of the validation and the test hours."""


def _eligibility(panel: pl.DataFrame, windows: dict[str, str | int]) -> pl.DataFrame:
    validation_start = datetime.fromisoformat(str(windows["validation_start"])).replace(tzinfo=UTC)
    test_start = datetime.fromisoformat(str(windows["test_start"])).replace(tzinfo=UTC)
    test_end = datetime.fromisoformat(str(windows["test_end"])).replace(tzinfo=UTC) + timedelta(days=1)
    valid_hours = float((test_start - validation_start).total_seconds() // 3600)
    test_hours = float((test_end - test_start).total_seconds() // 3600)
    hour_after = pl.col("utc_hour") - pl.duration(hours=1)
    return (
        panel.group_by("authority")
        .agg(
            (pl.col("demand").is_not_null() & (hour_after >= validation_start) & (hour_after < test_start))
            .sum()
            .alias("validation_hours"),
            (pl.col("demand").is_not_null() & (hour_after >= test_start) & (hour_after < test_end))
            .sum()
            .alias("test_hours"),
        )
        .with_columns(
            (pl.col("validation_hours") / valid_hours).alias("validation_coverage"),
            (pl.col("test_hours") / test_hours).alias("test_coverage"),
        )
        .with_columns(
            (
                (pl.col("validation_coverage") >= MINIMUM_WINDOW_COVERAGE)
                & (pl.col("test_coverage") >= MINIMUM_WINDOW_COVERAGE)
            ).alias("backtest_eligible")
        )
        .select("authority", "validation_coverage", "test_coverage", "backtest_eligible")
    )


def _subregion_gap(panel: pl.DataFrame, subregions: pl.DataFrame) -> pl.DataFrame:
    """Per authority with subregions: how far the subregion total sits from the authority's demand."""
    totals = (
        subregions.group_by(["authority", "utc_hour"])
        .agg(
            pl.col("demand").sum().alias("subregion_total"),
            pl.col("demand").is_null().sum().alias("missing_parts"),
        )
        .filter(pl.col("missing_parts") == 0)
    )
    joined = totals.join(
        panel.select("authority", "utc_hour", "demand"), on=["authority", "utc_hour"], how="inner"
    )
    joined = joined.filter(pl.col("demand").is_not_null() & (pl.col("demand") > 0))
    return (
        joined.with_columns(((pl.col("subregion_total") - pl.col("demand")) / pl.col("demand")).alias("gap"))
        .group_by("authority")
        .agg(
            pl.len().alias("hours"),
            pl.col("gap").abs().mean().alias("mean_abs_gap"),
            pl.col("gap").abs().median().alias("median_abs_gap"),
            pl.col("gap").mean().alias("mean_gap"),
        )
        .sort("authority")
    )


def _eia_figures(
    w: Scribe,
    manifest: Manifest,
    balance_files: list[eia930.SixMonthFile],
    subregion_files: list[eia930.SixMonthFile],
    authorities: pl.DataFrame,
    quarantined: quarantine.Quarantined,
    panel: pl.DataFrame,
    subregions: pl.DataFrame | None,
    hierarchy: pl.DataFrame,
    windows: dict[str, str | int],
    gap: pl.DataFrame | None,
) -> None:
    w.put("data.eia.balance_files", len(balance_files), "int")
    w.put("data.eia.subregion_files", len(subregion_files), "int")
    w.put("data.eia.first_half", balance_files[0].label, "text")
    w.put("data.eia.latest_half", balance_files[-1].label, "text")
    w.put("data.eia.authorities_in_files", authorities.height, "int")
    w.put("data.eia.demand_authorities", int(authorities["reports_demand"].sum()), "int")
    w.put("data.eia.generation_only_authorities", int((~authorities["reports_demand"]).sum()), "int")
    w.put(
        "data.eia.generation_only_list",
        ", ".join(authorities.filter(~pl.col("reports_demand"))["authority"].to_list()) or "none",
        "text",
    )
    eligible = authorities.filter(pl.col("backtest_eligible"))
    excluded = authorities.filter(pl.col("reports_demand") & ~pl.col("backtest_eligible"))
    w.put("data.eia.backtest_authorities", eligible.height, "int")
    w.put("data.eia.backtest_excluded", excluded.height, "int")
    w.put("data.eia.backtest_excluded_list", ", ".join(excluded["authority"].to_list()) or "none", "text")
    w.put("data.eia.minimum_window_coverage", MINIMUM_WINDOW_COVERAGE, "pct0")
    w.put("data.eia.panel_rows", panel.height, "int")
    w.put("data.eia.quarantined_rows", int(panel["quarantined"].sum()), "int")
    w.put("data.eia.quarantined_share", float(panel["quarantined"].sum()) / panel.height, "pct3")
    w.put("data.eia.revisions", quarantined.revisions, "int")
    for rule in quarantine.RULES:
        if rule == "revision":
            continue
        w.put(f"data.eia.quarantine.{rule}", int(panel[rule].sum()), "int")
    w.put("data.eia.spike_multiple", POLICY.spike_multiple_of_rolling_median, "float1")
    w.put("data.eia.rolling_median_days", POLICY.rolling_median_days, "int")
    first = panel["utc_hour"].min()
    last = panel["utc_hour"].max()
    w.put("data.eia.first_hour", str(first), "text")
    w.put("data.eia.last_hour", str(last), "text")
    for key, value in windows.items():
        w.put(f"data.windows.{key}", value, "int" if key.endswith("days") else "text")
    w.put("data.hierarchy.nodes", hierarchy.height, "int")
    w.put("data.hierarchy.regions", hierarchy.filter(pl.col("level") == 2).height, "int")
    w.put("data.hierarchy.authorities", hierarchy.filter(pl.col("level") == 3).height, "int")
    w.put("data.hierarchy.subregions", hierarchy.filter(pl.col("level") == 4).height, "int")
    w.put(
        "data.hierarchy.authorities_with_subregions",
        hierarchy.filter(pl.col("level") == 4)["parent"].n_unique() if subregions is not None else 0,
        "int",
    )
    rows: list[list[Scalar]] = []
    for row in quarantined.report.sort("authority").iter_rows(named=True):
        rows.append(
            [
                row["authority"],
                row["hours"],
                row["demand_missing"],
                row["demand_nonpositive"],
                row["demand_spike"],
                row["duplicate_hour"],
                row["missing_hour"],
                row["forecast_missing"],
                row["quarantined"],
                row["quarantined"] / row["hours"],
            ]
        )
    w.table(
        "data.quarantine_by_authority",
        [
            "Authority",
            "Hours",
            "Demand missing",
            "Zero or negative",
            "Spike",
            "Duplicated hour",
            "Missing hour",
            "Operator forecast missing",
            "Quarantined",
            "Share",
        ],
        ["text", "int", "int", "int", "int", "int", "int", "int", "int", "pct2"],
        rows,
    )
    if gap is not None and gap.height:
        w.put("data.subregion_gap.mean_abs_pct", as_float(gap["mean_abs_gap"].mean()), "pct2")
        w.put(
            "data.subregion_gap.worst_authority",
            str(gap.sort("mean_abs_gap", descending=True)["authority"][0]),
            "text",
        )
        w.put("data.subregion_gap.worst_abs_pct", as_float(gap["mean_abs_gap"].max()), "pct2")
        w.table(
            "data.subregion_gap",
            ["Authority", "Hours compared", "Mean absolute gap", "Median absolute gap", "Mean signed gap"],
            ["text", "int", "pct2", "pct2", "spct1"],
            [
                [r["authority"], r["hours"], r["mean_abs_gap"], r["median_abs_gap"], r["mean_gap"]]
                for r in gap.iter_rows(named=True)
            ],
        )
    auth_rows: list[list[Scalar]] = [
        [
            r["authority"],
            r["region"] or "none",
            "yes" if r["reports_demand"] else "no",
            r["hours"],
            r["demand_share"],
            r["validation_coverage"],
            r["test_coverage"],
            "yes" if r["backtest_eligible"] else "no",
        ]
        for r in authorities.sort("authority").iter_rows(named=True)
    ]
    w.table(
        "data.authorities",
        [
            "Authority",
            "Region",
            "Reports demand",
            "Hours in files",
            "Share of its span with demand",
            "Validation coverage",
            "Test coverage",
            "In the backtest",
        ],
        ["text", "text", "text", "int", "pct1", "pct1", "pct1", "text"],
        auth_rows,
    )


def _london(paths: Paths, manifest: Manifest, require: bool) -> None:
    w = Scribe(
        manifest,
        source="real:lcl",
        population="the Low Carbon London release",
        origin="lookahead_registry.stages.data",
    )
    folder = paths.external_london
    checks_path = paths.london / "checks.json"
    raw_present = (
        (folder / london.RAW_ZIP).exists()
        or (folder / london.RAW_CSV).exists()
        or (folder / london.READINGS).exists()
    )
    if raw_present and not checks_path.exists():
        # The checks read all 167 million rows once; the result is committed and reused until removed.
        readings = london.to_parquet(folder)
        result = london.checks(readings)
        paths.london.mkdir(parents=True, exist_ok=True)
        checks_path.write_text(json.dumps(asdict(result), indent=1) + "\n", encoding="utf-8")
    elif checks_path.exists():
        result = london.LondonChecks(**json.loads(checks_path.read_text(encoding="utf-8")))
    elif require:
        raise DataMissing(f"the London release is not under {folder} and no committed checks exist")
    else:
        w.put("data.london.status", "not read", "text")
        return
    w.put("data.london.status", "read in full", "text")
    w.put("data.london.rows", result.rows, "int")
    w.put("data.london.households", result.households, "int")
    w.put("data.london.tou_households", result.tou_households, "int")
    w.put("data.london.std_households", result.std_households, "int")
    w.put("data.london.first", result.first, "text")
    w.put("data.london.last", result.last, "text")
    w.put("data.london.null_readings", result.null_readings, "int")
    w.put("data.london.duplicate_readings", result.duplicate_readings, "int")
    w.put("data.london.missing_half_hours", result.missing_half_hours, "int")


def load_windows(paths: Paths) -> dict[str, str | int]:
    path = paths.eia / "windows.json"
    if not path.exists():
        raise DataMissing("data/eia930/windows.json is missing; run `make data` first")
    loaded: dict[str, str | int] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def load_panel(paths: Paths) -> pl.DataFrame:
    """The committed panel with the clean demand column rebuilt from the raw demand and the flags."""
    path = paths.eia / "hourly.parquet"
    if not path.exists():
        raise DataMissing("data/eia930/hourly.parquet is missing; run `make data` first")
    panel = pl.read_parquet(path)
    if "demand" not in panel.columns:
        panel = panel.with_columns(
            pl.when(pl.col("quarantined"))
            .then(None)
            .otherwise(pl.col("demand_raw"))
            .cast(pl.Float64)
            .alias("demand")
        )
    return panel


def load_hierarchy(paths: Paths) -> pl.DataFrame:
    path: Path = paths.data / "hierarchy.csv"
    if not path.exists():
        raise DataMissing("data/hierarchy.csv is missing; run `make data` first")
    return pl.read_csv(path)
