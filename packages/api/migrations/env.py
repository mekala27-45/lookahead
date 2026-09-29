"""Alembic environment: the database URL comes from DATABASE_URL, the schema from the SQLModel tables."""

from __future__ import annotations

import os

import lookahead_api.db  # noqa: F401  (registers the tables on SQLModel.metadata)
from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlmodel import SQLModel

config = context.config
config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/lookahead"),
)
target_metadata = SQLModel.metadata
SCHEMA = os.environ.get("LOOKAHEAD_DB_SCHEMA", "").strip()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section) or {}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        if SCHEMA:
            # The tables and alembic's own version table live in the schema, so another project's
            # tables in the same database are never touched.
            connection.execute(text(f'create schema if not exists "{SCHEMA}"'))
            connection.execute(text(f'set search_path to "{SCHEMA}", public'))
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
