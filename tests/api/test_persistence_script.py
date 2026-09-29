"""The out of process check, driven against a server this test starts, exactly as CI runs it."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.postgres


def test_check_persistence_starts_a_server_and_reads_back_independently(
    database_url: str, results: Path
) -> None:
    # The script migrates with alembic, so it starts from an empty database rather than one the
    # fixtures created with the SQLModel metadata.
    from lookahead_api.db import SQLModel, make_engine
    from sqlalchemy import text

    engine = make_engine(database_url)
    SQLModel.metadata.drop_all(engine)
    with engine.begin() as connection:
        connection.execute(text("drop table if exists alembic_version"))
    engine.dispose()
    env = {**os.environ, "LOOKAHEAD_TEST_DATABASE_URL": database_url, "LOOKAHEAD_WRITE_TOKEN": "check-token"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_persistence.py"), "--start-server", "--port", "8791"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "read back from outside the server process" in proc.stdout
    assert '"audit_before_response": true' in proc.stdout


def test_migration_into_a_schema_ignores_another_projects_version_table(database_url: str) -> None:
    """The one free database is shared with another project whose alembic version table sits in
    public at the same revision id. The migration must keep its own version table in the schema
    and create the tables there, rather than reading the other project's revision through the
    search path and doing nothing (which is what the first deploy did)."""
    import psycopg

    from tests.api.conftest import plain_url

    schema = "lookahead_alembic_test"
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(f"drop schema if exists {schema} cascade")
        cur.execute("create table if not exists public.alembic_version (version_num varchar(32) primary key)")
        cur.execute("delete from public.alembic_version")
        cur.execute("insert into public.alembic_version (version_num) values ('0001')")
    env = {**os.environ, "DATABASE_URL": database_url, "LOOKAHEAD_DB_SCHEMA": schema}
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "packages" / "api" / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=ROOT / "packages" / "api",
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    with psycopg.connect(plain_url(database_url), autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "select table_name from information_schema.tables where table_schema = %s order by 1", (schema,)
        )
        tables = [r[0] for r in cur.fetchall()]
        cur.execute("drop table public.alembic_version")
        cur.execute(f"drop schema {schema} cascade")
    assert "forecasts" in tables and "alembic_version" in tables, tables
