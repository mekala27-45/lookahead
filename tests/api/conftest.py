"""API fixtures: a real Postgres, the served model export, and a client with the write token.

Every test that checks persistence reads back through a psycopg connection opened for the
purpose, never through the application's session: a shared session cannot see a missing
commit, which is the bug Day 5 of this series found and every day since has tested for.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from lookahead_api.app import create_app
from lookahead_api.db import SQLModel, make_engine
from lookahead_api.settings import Settings

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "test-token-not-a-secret"
DEFAULT_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/lookahead_test"


def _url() -> str:
    return os.environ.get("LOOKAHEAD_TEST_DATABASE_URL", DEFAULT_URL)


def plain_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


def rows(url: str, sql: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Read through a connection this call opens and closes: independent of the app's session."""
    with psycopg.connect(plain_url(url)) as conn, conn.cursor() as cur:
        cur.execute(sql, params)  # type: ignore[arg-type]
        return list(cur.fetchall())


@pytest.fixture(scope="session")
def database_url() -> str:
    url = _url()
    try:
        with psycopg.connect(plain_url(url), connect_timeout=3):
            pass
    except psycopg.OperationalError:
        if os.environ.get("LOOKAHEAD_REQUIRE_POSTGRES"):
            pytest.fail(f"LOOKAHEAD_REQUIRE_POSTGRES is set but no Postgres answers at {url}")
        pytest.skip(f"no Postgres reachable at {url}")
    return url


@pytest.fixture(scope="session")
def results() -> Path:
    folder = ROOT / "results"
    if (
        not (folder / "models" / "own_model.json").exists()
        or not (folder / "models" / "serving_bundle.parquet").exists()
    ):
        if os.environ.get("LOOKAHEAD_REQUIRE_MODEL"):
            pytest.fail("LOOKAHEAD_REQUIRE_MODEL is set but results/models has no export")
        pytest.skip("no served model export under results/models; run `lookahead backtest --backend own`")
    return folder


@pytest.fixture()
def clean_db(database_url: str) -> str:
    engine = make_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    return database_url


@pytest.fixture()
def settings(clean_db: str, results: Path) -> Settings:
    return Settings(database_url=clean_db, write_token=TOKEN, results=results, environment="test")


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture()
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}"}
