"""Three tests per text gate: it passes clean input, it fails on the defect it exists for,
and it refuses to report a pass when it was given nothing to check."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_no_em_dash, check_statement, check_vocabulary, scan_for_planted_identifiers

ROOT = Path(__file__).resolve().parents[2]
STATEMENT_TEXT = (
    "Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, "
    "public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' "
    "Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid "
    "operations."
)


# The dash gate


def test_dash_gate_passes_clean_file(tmp_path: Path) -> None:
    clean = tmp_path / "clean.md"
    clean.write_text("Ranges are written with to, asides with commas.\n", encoding="utf-8")
    assert check_no_em_dash.check(tmp_path, [clean]) == 1


def test_dash_gate_fails_on_em_dash(tmp_path: Path) -> None:
    dirty = tmp_path / "dirty.md"
    dirty.write_text("A sentence " + chr(0x2014) + " with the defect.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="em dash"):
        check_no_em_dash.check(tmp_path, [dirty])


def test_dash_gate_refuses_to_pass_on_nothing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no files"):
        check_no_em_dash.check(tmp_path, [])


def test_dash_gate_passes_the_repository() -> None:
    assert check_no_em_dash.check(ROOT) > 10


# The vocabulary gate


def test_vocabulary_gate_passes_clean_file(tmp_path: Path) -> None:
    clean = tmp_path / "clean.md"
    clean.write_text("The forecast is graded by its worst hour, not its average.\n", encoding="utf-8")
    assert check_vocabulary.check(tmp_path, [clean]) == 1


def test_vocabulary_gate_fails_on_filler(tmp_path: Path) -> None:
    dirty = tmp_path / "dirty.md"
    dirty.write_text("We " + "lever" + "age a " + "seam" + "less platform.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="vocabulary gate failed"):
        check_vocabulary.check(tmp_path, [dirty])


def test_vocabulary_gate_refuses_to_pass_on_nothing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no files"):
        check_vocabulary.check(tmp_path, [])


def test_vocabulary_gate_passes_the_repository() -> None:
    assert check_vocabulary.check(ROOT) > 10


# The statement gate


def test_statement_gate_passes_surface_with_statement(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text(
        f"<html><body><p>Numbers.</p><footer>{STATEMENT_TEXT}</footer></body></html>", encoding="utf-8"
    )
    assert check_statement.check(tmp_path, [page]) == 1


def test_statement_gate_fails_surface_without_statement(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text("# A page with numbers and no statement\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing the statement"):
        check_statement.check(tmp_path, [page])


def test_statement_gate_ignores_statement_hidden_in_script(tmp_path: Path) -> None:
    page = tmp_path / "page.html"
    page.write_text(
        f"<html><body><script>const s = '{STATEMENT_TEXT}';</script></body></html>", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="missing the statement"):
        check_statement.check(tmp_path, [page])


def test_statement_gate_refuses_to_pass_on_nothing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no surfaces"):
        check_statement.check(tmp_path, [])


# The identifier scan


def test_identifier_scan_passes_clean_results(tmp_path: Path) -> None:
    clean = tmp_path / "results.json"
    clean.write_text('{"mape": 2.41, "authority": "PJM"}', encoding="utf-8")
    assert scan_for_planted_identifiers.check(tmp_path, [clean], planted=set()) == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("card 4111 1111 1111 1111 on file", "card number ending 1111"),
        ("ssn 123-45-6789", "SSN pattern"),
        ("mail someone@realmail.net", "email address"),
        (
            "LCLid,stdorToU,DateTime,KWH/hh (per half hour)\nMAC000002,Std,2012-10-12 00:30:00.0000000, 0 \n",
            "london raw header",
        ),
        (
            "Balancing Authority,Data Date,Hour Number,Local Time at End of Hour,UTC Time at End of Hour,"
            "Demand Forecast (MW),Demand (MW),Net Generation (MW),Total Interchange (MW)\n",
            "eia balance raw header",
        ),
        ("household plantedperson_quiddle used twice", "planted identifier"),
    ],
)
def test_identifier_scan_finds_each_planted_kind(tmp_path: Path, text: str, expected: str) -> None:
    planted = tmp_path / "planted.md"
    planted.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=expected):
        scan_for_planted_identifiers.check(tmp_path, [planted], planted={"plantedperson_quiddle"})


def test_identifier_scan_finds_planted_token_in_parquet(tmp_path: Path) -> None:
    import polars as pl

    path = tmp_path / "table.parquet"
    pl.DataFrame({"authority": ["PJM", "plantedperson_quiddle"], "mape": [1.0, 2.0]}).write_parquet(path)
    with pytest.raises(ValueError, match="planted identifier"):
        scan_for_planted_identifiers.check(tmp_path, [path], planted={"plantedperson_quiddle"})


def test_identifier_scan_allows_example_domain_addresses(tmp_path: Path) -> None:
    clean = tmp_path / "docs.md"
    clean.write_text("Write to desk@lookahead.example for the plan.", encoding="utf-8")
    assert scan_for_planted_identifiers.check(tmp_path, [clean], planted=set()) == 1


def test_identifier_scan_refuses_to_pass_on_nothing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no files"):
        scan_for_planted_identifiers.check(tmp_path, [], planted=set())


def test_identifier_scan_reads_the_planted_list() -> None:
    assert "plantedperson_quiddle" in scan_for_planted_identifiers.load_planted(ROOT)


def test_identifier_scan_passes_the_repository() -> None:
    assert scan_for_planted_identifiers.check(ROOT) >= 1
