"""Shared fixtures and the availability probes behind the named skip markers."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _importable(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _external_ready() -> bool:
    eia = ROOT / "data" / "external" / "eia930"
    london = ROOT / "data" / "external" / "london"
    return any(eia.glob("EIA930_BALANCE_*.csv*")) and any(london.glob("LCL-FullData*"))


def _derived_ready() -> bool:
    return (ROOT / "data" / "eia930" / "hourly.parquet").exists() and (
        ROOT / "data" / "weather" / "hourly.parquet"
    ).exists()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    external_ready = _external_ready()
    derived_ready = _derived_ready()
    xgb_ready = _importable("xgboost")
    for item in items:
        if "external" in item.keywords and not external_ready:
            if os.environ.get("LOOKAHEAD_REQUIRE_EXTERNAL"):
                pytest.fail("LOOKAHEAD_REQUIRE_EXTERNAL is set but the raw files are not under data/external")
            item.add_marker(pytest.mark.skip(reason="the raw public files are not under data/external"))
        if "derived" in item.keywords and not derived_ready:
            if os.environ.get("LOOKAHEAD_REQUIRE_DERIVED"):
                pytest.fail("LOOKAHEAD_REQUIRE_DERIVED is set but the derived tables are missing")
            item.add_marker(pytest.mark.skip(reason="the derived tables under data/ are missing"))
        if "xgboost" in item.keywords and not xgb_ready:
            if os.environ.get("LOOKAHEAD_REQUIRE_XGBOOST"):
                pytest.fail("LOOKAHEAD_REQUIRE_XGBOOST is set but xgboost does not import")
            item.add_marker(pytest.mark.skip(reason="xgboost is not importable"))


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT
