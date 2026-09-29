"""Runtime settings, read from the environment once."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str
    write_token: str
    results: Path
    environment: str
    cors_origins: tuple[str, ...] = ()
    schema: str = ""
    """A Postgres schema for the tables, so the API can share a database with another project's
    tables (the free Neon allowance is one project); empty means the default search path."""

    @property
    def token_required(self) -> bool:
        return bool(self.write_token)

    @property
    def served_path(self) -> Path:
        """The registry's choice of backend; own until the registry stage has run."""
        return self.results / "registry" / "served.json"

    @property
    def models(self) -> Path:
        return self.results / "models"

    @property
    def bundle_path(self) -> Path:
        return self.models / "serving_bundle.parquet"


def load_settings() -> Settings:
    root = Path(os.environ.get("LOOKAHEAD_ROOT", Path(__file__).resolve().parents[4]))
    return Settings(
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/lookahead"
        ),
        write_token=os.environ.get("LOOKAHEAD_WRITE_TOKEN", ""),
        results=root / "results",
        environment=os.environ.get("LOOKAHEAD_ENV", "development"),
        cors_origins=tuple(
            o.strip() for o in os.environ.get("LOOKAHEAD_CORS_ORIGINS", "*").split(",") if o.strip()
        ),
        schema=os.environ.get("LOOKAHEAD_DB_SCHEMA", "").strip(),
    )
