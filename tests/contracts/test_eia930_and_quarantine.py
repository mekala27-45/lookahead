"""The EIA reader, the seven quarantine rules (each catches its defect, passes clean data,
refuses an empty frame), the hierarchy table and the windows."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import polars as pl
import pytest
from lookahead_contracts import eia930, quarantine
from lookahead_contracts.hierarchy_table import build_hierarchy, leaves
from lookahead_core.paths import Paths
from lookahead_registry.stages import data as data_stage

from tests.contracts.fixtures import utc, write_balance, write_subregion

START = utc(2018, 6, 30, 23)
AUTHORITIES = {"PJM": "MIDA", "ERCO": "TEX", "CISO": "CAL"}


def _clean(tmp_path: Path, hours: int = 24 * 40, **kwargs: object) -> pl.DataFrame:
    path = write_balance(tmp_path / "EIA930_BALANCE_2018_Jul_Dec.csv", AUTHORITIES, START, hours, **kwargs)  # type: ignore[arg-type]
    return eia930.read_balance(path)


def test_reader_parses_numbers_with_separators_and_both_time_formats(tmp_path: Path) -> None:
    frame = _clean(tmp_path, hours=48)
    assert frame.height == 48 * 3
    assert frame["demand"].dtype == pl.Float64
    assert frame["demand"].min() > 5_000
    assert str(frame["utc_hour"].dtype) == "Datetime(time_unit='us', time_zone='UTC')"
    assert frame["utc_offset_hours"].unique().to_list() == [-5]
    iso = write_balance(tmp_path / "iso.csv", {"PJM": "MIDA"}, START, 24, time_format="%Y-%m-%dT%H:%M:%S")
    assert eia930.read_balance(iso)["utc_hour"][0] == frame["utc_hour"][0]


def test_reader_refuses_a_file_without_the_demand_column(tmp_path: Path) -> None:
    path = tmp_path / "EIA930_BALANCE_2018_Jul_Dec.csv"
    path.write_text("Balancing Authority,UTC Time at End of Hour\nPJM,07/01/2018 01:00:00 AM\n")
    with pytest.raises(ValueError, match="lacks the columns"):
        eia930.read_balance(path)


def test_discover_orders_half_years_and_prefers_csv(tmp_path: Path) -> None:
    for name in (
        "EIA930_BALANCE_2019_Jan_Jun.csv.gz",
        "EIA930_BALANCE_2018_Jul_Dec.csv",
        "EIA930_BALANCE_2018_Jul_Dec.csv.gz",
        "EIA930_SUBREGION_2018_Jul_Dec.csv",
    ):
        (tmp_path / name).write_text("x")
    found = eia930.discover_files(tmp_path)
    assert [f.label for f in found if f.kind == "BALANCE"] == ["2018_Jul_Dec", "2019_Jan_Jun"]
    assert found[0].path.suffix == ".csv"
    assert eia930.check_halves_complete(found, "BALANCE", "2018_Jul_Dec") == []
    (tmp_path / "EIA930_BALANCE_2020_Jan_Jun.csv").write_text("x")
    assert eia930.check_halves_complete(eia930.discover_files(tmp_path), "BALANCE", "2018_Jul_Dec") == [
        "2019_Jul_Dec"
    ]


def test_clean_panel_has_no_quarantined_rows(tmp_path: Path) -> None:
    result = quarantine.apply_rules(_clean(tmp_path))
    assert int(result.panel["quarantined"].sum()) == 0
    assert result.revisions == 0
    quarantine.check_report_matches_panel(result.panel, result.report)


@pytest.mark.parametrize(
    ("defect", "rule"),
    [
        ("missing", "demand_missing"),
        ("zero", "demand_nonpositive"),
        ("negative", "demand_nonpositive"),
        ("spike", "demand_spike"),
        ("duplicate", "duplicate_hour"),
        ("skip", "missing_hour"),
        ("forecast_missing", "forecast_missing"),
        ("forecast_negative", "forecast_nonpositive"),
    ],
)
def test_each_rule_catches_its_defect(tmp_path: Path, defect: str, rule: str) -> None:
    frame = _clean(tmp_path, defects={("PJM", 24 * 20): defect})
    result = quarantine.apply_rules(frame)
    hit = result.panel.filter(pl.col(rule))
    assert hit.height == 1
    assert hit["authority"][0] == "PJM"
    assert hit["utc_hour"][0] == START + timedelta(hours=24 * 20 + 1)
    if rule not in ("forecast_missing", "forecast_nonpositive"):
        assert hit["demand"][0] is None, "the clean demand is null where a rule fired"
    if rule == "forecast_nonpositive":
        assert hit["forecast_operator"][0] is None, "a forecast at or below zero is treated as unpublished"
    if rule not in ("missing_hour", "forecast_missing", "forecast_nonpositive"):
        assert int(result.report.filter(pl.col("authority") == "PJM")[rule][0]) == 1
    quarantine.check_report_matches_panel(result.panel, result.report)


def test_a_missing_hour_is_inserted_not_ignored(tmp_path: Path) -> None:
    frame = _clean(tmp_path, defects={("PJM", 100): "skip"})
    assert frame.filter(pl.col("authority") == "PJM").height == 24 * 40 - 1
    result = quarantine.apply_rules(frame)
    assert result.panel.filter(pl.col("authority") == "PJM").height == 24 * 40


def test_a_later_file_revises_an_earlier_hour(tmp_path: Path) -> None:
    first = eia930.read_balance(
        write_balance(tmp_path / "EIA930_BALANCE_2018_Jul_Dec.csv", {"PJM": "MIDA"}, START, 48, seed=1)
    )
    second = eia930.read_balance(
        write_balance(tmp_path / "EIA930_BALANCE_2019_Jan_Jun.csv", {"PJM": "MIDA"}, START, 48, seed=2)
    )
    result = quarantine.apply_rules(eia930.concat_in_order([first, second]))
    assert result.revisions == 48
    assert result.panel.height == 48
    kept = result.panel["demand_raw"].to_list()
    assert kept == second["demand"].to_list(), "the later file's values are kept"


def test_quarantine_refuses_an_empty_frame() -> None:
    with pytest.raises(quarantine.QuarantineError, match="empty"):
        quarantine.apply_rules(
            pl.DataFrame(
                schema={
                    "authority": pl.Utf8,
                    "utc_hour": pl.Datetime,
                    "demand": pl.Float64,
                    "forecast_operator": pl.Float64,
                    "source_file": pl.Utf8,
                }
            )
        )


def test_report_mismatch_is_caught(tmp_path: Path) -> None:
    result = quarantine.apply_rules(_clean(tmp_path, defects={("PJM", 30): "zero"}))
    tampered = result.report.with_columns(pl.lit(0).alias("demand_nonpositive"))
    with pytest.raises(quarantine.QuarantineError, match="demand_nonpositive"):
        quarantine.check_report_matches_panel(result.panel, tampered)


def test_generation_only_authorities_are_excluded_by_rule(tmp_path: Path) -> None:
    frame = _clean(tmp_path, hours=48, generation_only=("CISO",))
    reporters = eia930.demand_reporters(frame)
    assert reporters.filter(pl.col("authority") == "CISO")["reports_demand"][0] is False
    assert reporters.filter(pl.col("authority") == "PJM")["reports_demand"][0] is True


def test_hierarchy_levels_parents_and_leaves() -> None:
    regions = pl.DataFrame(
        {"authority": ["PJM", "ERCO", "CISO", "DUK"], "region": ["MIDA", "TEX", "CAL", "CAR"]}
    )
    subs = pl.DataFrame({"authority": ["PJM", "PJM", "CISO"], "subregion": ["AE", "PE", "PGAE"]})
    h = build_hierarchy(regions, subs)
    assert h.filter(pl.col("level") == 0)["node"].to_list() == ["US48"]
    assert set(h.filter(pl.col("level") == 1)["node"].to_list()) == {"Eastern", "Western", "Texas"}
    assert h.filter(pl.col("node") == "PJM")["parent"][0] == "MIDA"
    assert h.filter(pl.col("node") == "MIDA")["parent"][0] == "Eastern"
    assert h.filter(pl.col("node") == "PJM.AE")["parent"][0] == "PJM"
    assert sorted(leaves(h)) == ["CISO.PGAE", "DUK", "ERCO", "PJM.AE", "PJM.PE"]


def test_hierarchy_refuses_an_unknown_region() -> None:
    with pytest.raises(ValueError, match="interconnection"):
        build_hierarchy(pl.DataFrame({"authority": ["X"], "region": ["MARS"]}), None)


def test_data_stage_end_to_end_on_fixture_files(tmp_path: Path) -> None:
    root = tmp_path
    p = Paths(root=root)
    p.external_eia.mkdir(parents=True)
    hours = 24 * 800
    write_balance(
        p.external_eia / "EIA930_BALANCE_2018_Jul_Dec.csv",
        AUTHORITIES,
        START,
        hours,
        defects={("PJM", 50): "zero"},
        bases={"PJM": 10_000.0},
    )
    write_subregion(
        p.external_eia / "EIA930_SUBREGION_2018_Jul_Dec.csv", {"PJM": {"AE": 0.4, "PE": 0.58}}, START, hours
    )
    manifest = data_stage.run(p, "2026-09-29", 1, require_london=False)
    assert (p.eia / "hourly.parquet").exists()
    assert (p.data / "hierarchy.csv").exists()
    windows = data_stage.load_windows(p)
    assert windows["test_end"] > windows["test_start"] > windows["validation_start"]
    assert manifest.raw("data.eia.demand_authorities") == 3
    assert manifest.raw("data.eia.quarantine.demand_nonpositive") == 1
    assert manifest.raw("data.hierarchy.subregions") == 2
    gap = manifest.raw("data.subregion_gap.mean_abs_pct")
    assert isinstance(gap, float) and 0.015 < gap < 0.025, (
        "the subregion total sits two percent under the authority"
    )
    assert manifest.raw("data.london.status") == "not read"
