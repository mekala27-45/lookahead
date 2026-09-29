"""Tables for everything the API persists across a request boundary: issued forecasts and
their rows, scores, the model list and the audit log. Every one of them is observed from an
independently opened connection in the tests, because a test that shares the application's
session cannot see a missing commit (Day 5 of this series found exactly that bug)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import Field, Session, SQLModel, create_engine, select


def now() -> datetime:
    return datetime.now(UTC)


class Forecast(SQLModel, table=True):
    __tablename__ = "forecasts"
    id: int | None = Field(default=None, primary_key=True)
    forecast_id: str = Field(index=True, unique=True)
    authority: str = Field(index=True)
    origin: datetime = Field(index=True)
    model_version: str
    backend: str
    spec_hash: str
    data_source: str
    horizons: int
    note: str = ""
    issued_at: datetime = Field(default_factory=now)
    scored_at: datetime | None = None
    scored_rows: int = 0


class ForecastRow(SQLModel, table=True):
    __tablename__ = "forecast_rows"
    id: int | None = Field(default=None, primary_key=True)
    forecast_id: str = Field(foreign_key="forecasts.forecast_id", index=True)
    horizon: int
    target_hour: datetime
    q05: float
    q25: float
    q50: float
    q75: float
    q95: float


class Score(SQLModel, table=True):
    __tablename__ = "scores"
    id: int | None = Field(default=None, primary_key=True)
    forecast_id: str = Field(foreign_key="forecasts.forecast_id", index=True)
    horizon: int
    target_hour: datetime
    actual: float
    abs_pct_error: float
    inside_50: bool
    inside_90: bool
    pinball_q05: float
    pinball_q25: float
    pinball_q50: float
    pinball_q75: float
    pinball_q95: float
    scored_at: datetime = Field(default_factory=now)


class ModelRow(SQLModel, table=True):
    __tablename__ = "models"
    id: int | None = Field(default=None, primary_key=True)
    version: str = Field(index=True, unique=True)
    backend: str
    spec_hash: str
    served: bool = False
    gates: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    registered_at: datetime = Field(default_factory=now)


class AuditEntry(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=now, index=True)
    actor: str
    action: str
    resource: str
    resource_id: str = ""
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


def connect_args(schema: str = "") -> dict[str, Any]:
    """With a schema, every connection searches it first, so the tables live there and the SQL
    stays unqualified."""
    if not schema:
        return {}
    return {"options": f"-c search_path={schema},public"}


def make_async_engine(url: str, schema: str = "") -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True, connect_args=connect_args(schema))


def make_engine(url: str, schema: str = "") -> Any:
    return create_engine(url, pool_pre_ping=True, connect_args=connect_args(schema))


def ensure_schema(url: str, schema: str) -> None:
    """Create the schema when it is missing, through a plain connection."""
    if not schema:
        return
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as connection:
        connection.execute(text(f'create schema if not exists "{schema}"'))
    engine.dispose()


def create_all(engine: Any) -> None:
    SQLModel.metadata.create_all(engine)


def reset_notes(engine: Any, notes: tuple[str, ...]) -> dict[str, int]:
    """Delete the forecasts the demo recording and the checks issued, by their stated notes, with
    their rows and scores; the audit log is left alone."""
    counts = {"forecasts": 0, "rows": 0, "scores": 0}
    with Session(engine) as session:
        forecasts = session.exec(select(Forecast).where(Forecast.note.in_(notes))).all()  # type: ignore[attr-defined]
        for f in forecasts:
            for row in session.exec(
                select(ForecastRow).where(ForecastRow.forecast_id == f.forecast_id)
            ).all():
                session.delete(row)
                counts["rows"] += 1
            for score in session.exec(select(Score).where(Score.forecast_id == f.forecast_id)).all():
                session.delete(score)
                counts["scores"] += 1
            session.delete(f)
            counts["forecasts"] += 1
        session.commit()
    return counts
