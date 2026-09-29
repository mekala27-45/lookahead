"""The lookahead API: the forecast log.

``POST /v1/forecasts`` issues a forecast for an authority from the served model at the latest
origin the data allows, writes the forecast rows (one per horizon with the quantiles), the
model version, the spec hash and the origin, then the audit row, then returns the id.
``GET /v1/forecasts/{id}`` returns it with its scores if any. ``POST /v1/score`` scores every
stored forecast whose target hours now have actuals, writes the scores, and reports the share
still unscored. ``GET /v1/models`` lists the registry with the gate results. Writes need the
token; this is a demonstration and the README says so. Every response body carries the
statement. Every write goes: the rows, then the audit row, then commit, then the response.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from lookahead_core.config import QUANTILE_LEVELS
from lookahead_core.statements import STATEMENT
from lookahead_forecast.interface import QUANTILE_COLUMNS
from lookahead_forecast.serve import IssuedForecast, ServedModel
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from lookahead_api.db import AuditEntry, Forecast, ForecastRow, ModelRow, Score, make_async_engine
from lookahead_api.settings import Settings, load_settings


def envelope(data: dict[str, Any]) -> dict[str, Any]:
    return {**data, "statement": STATEMENT, "served_at": datetime.now(UTC).isoformat()}


class ForecastIn(BaseModel):
    authority: str = Field(min_length=1, max_length=16)
    note: str = Field(default="", max_length=200)


class ScoreIn(BaseModel):
    note: str = Field(default="", max_length=200)


class AppState:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine: AsyncEngine = make_async_engine(settings.database_url, settings.schema)
        self.model: ServedModel | None = None
        self.served_backend = "own"
        self.load_model()

    def load_model(self) -> None:
        if self.settings.served_path.exists():
            served = json.loads(self.settings.served_path.read_text(encoding="utf-8"))
            self.served_backend = str(served.get("backend", "own"))
        export = self.settings.models / f"{self.served_backend}_model.json"
        if export.exists() and self.settings.bundle_path.exists():
            self.model = ServedModel(export, self.settings.bundle_path)


def state_of(request: Request) -> AppState:
    state: AppState = request.app.state.lookahead
    return state


async def session_of(request: Request) -> AsyncIterator[AsyncSession]:
    async with AsyncSession(state_of(request).engine, expire_on_commit=False) as session:
        yield session


def actor_of(request: Request, authorization: Annotated[str | None, Header()] = None) -> str:
    settings = state_of(request).settings
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        if settings.token_required and token == settings.write_token:
            return "token"
    return "anonymous"


SessionDep = Annotated[AsyncSession, Depends(session_of)]
ActorDep = Annotated[str, Depends(actor_of)]


def require_writer(actor: str) -> None:
    if actor != "token":
        raise HTTPException(status_code=401, detail="writes need the token")


async def audit(
    session: AsyncSession,
    actor: str,
    action: str,
    resource: str,
    resource_id: str = "",
    detail: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEntry(
            actor=actor, action=action, resource=resource, resource_id=resource_id, detail=detail or {}
        )
    )
    await session.commit()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.lookahead = AppState(settings)
        yield
        await app.state.lookahead.engine.dispose()

    app = FastAPI(title="lookahead", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins) or ["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=envelope({"error": str(exc.detail)}))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content=envelope({"error": "invalid request", "detail": exc.errors()})
        )

    @app.get("/v1/health")
    async def health(request: Request, session: SessionDep) -> dict[str, Any]:
        state = state_of(request)
        database = "ok"
        try:
            await session.exec(select(Forecast.id).limit(1))
        except Exception:
            database = "unreachable"
        return envelope(
            {
                "status": "ok",
                "environment": state.settings.environment,
                "database": database,
                "model_version": state.model.version if state.model else None,
                "backend": state.model.backend if state.model else None,
                "authorities": len(state.model.authorities) if state.model else 0,
                "writes": "token gated",
            }
        )

    @app.get("/v1/models")
    async def models(request: Request, session: SessionDep) -> dict[str, Any]:
        state = state_of(request)
        rows = (await session.exec(select(ModelRow).order_by(col(ModelRow.registered_at)))).all()
        found = [
            {
                "version": r.version,
                "backend": r.backend,
                "spec_hash": r.spec_hash,
                "served": r.served,
                "gates": r.gates,
                "registered_at": r.registered_at.isoformat(),
            }
            for r in rows
        ]
        if not found:
            registry = state.settings.results / "registry" / "gates.json"
            if registry.exists():
                found = json.loads(registry.read_text(encoding="utf-8")).get("models", [])
        return envelope({"models": found, "serving": state.model.version if state.model else None})

    @app.get("/v1/authorities")
    async def authorities(request: Request) -> dict[str, Any]:
        state = state_of(request)
        if state.model is None:
            raise HTTPException(status_code=503, detail="no served model on this server")
        return envelope(
            {
                "authorities": [
                    {"authority": a, "latest_origin": state.model.latest_origin(a).isoformat()}
                    for a in state.model.authorities
                ]
            }
        )

    @app.post("/v1/forecasts", status_code=201)
    async def issue(
        body: ForecastIn, request: Request, session: SessionDep, actor: ActorDep
    ) -> dict[str, Any]:
        require_writer(actor)
        state = state_of(request)
        if state.model is None:
            raise HTTPException(status_code=503, detail="no served model on this server")
        if body.authority not in state.model.authorities:
            raise HTTPException(status_code=404, detail="unknown authority")
        issued = state.model.issue(body.authority)
        row = Forecast(
            forecast_id=str(uuid.uuid4()),
            authority=issued.authority,
            origin=issued.origin,
            model_version=issued.model_version,
            backend=issued.backend,
            spec_hash=issued.spec_hash,
            data_source=str(state.model.payload.get("data_source", "")),
            horizons=len(issued.horizons),
            note=body.note,
        )
        session.add(row)
        for i, (h, t) in enumerate(zip(issued.horizons, issued.target_hours, strict=True)):
            q = [float(issued.quantiles[i, k]) for k in range(len(QUANTILE_COLUMNS))]
            session.add(
                ForecastRow(
                    forecast_id=row.forecast_id,
                    horizon=h,
                    target_hour=t,
                    q05=q[0],
                    q25=q[1],
                    q50=q[2],
                    q75=q[3],
                    q95=q[4],
                )
            )
        await session.flush()
        await audit(
            session,
            actor,
            "issue",
            "forecast",
            row.forecast_id,
            {
                "authority": issued.authority,
                "origin": issued.origin.isoformat(),
                "model_version": issued.model_version,
            },
        )
        return envelope(
            {
                "forecast_id": row.forecast_id,
                **_forecast_payload(row, issued=issued),
                "stored_rows": len(issued.horizons),
            }
        )

    @app.get("/v1/forecasts")
    async def list_forecasts(
        session: SessionDep, authority: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        query = select(Forecast).order_by(col(Forecast.issued_at).desc()).limit(min(limit, 500))
        if authority:
            query = query.where(Forecast.authority == authority)
        rows = (await session.exec(query)).all()
        return envelope({"forecasts": [_forecast_payload(r) for r in rows]})

    @app.get("/v1/forecasts/{forecast_id}")
    async def get_forecast(forecast_id: str, session: SessionDep) -> dict[str, Any]:
        row = (await session.exec(select(Forecast).where(Forecast.forecast_id == forecast_id))).first()
        if row is None:
            raise HTTPException(status_code=404, detail="no forecast with that id")
        rows = (
            await session.exec(
                select(ForecastRow)
                .where(ForecastRow.forecast_id == forecast_id)
                .order_by(col(ForecastRow.horizon))
            )
        ).all()
        scores = (
            await session.exec(
                select(Score).where(Score.forecast_id == forecast_id).order_by(col(Score.horizon))
            )
        ).all()
        return envelope(
            {
                **_forecast_payload(row),
                "rows": [_row_payload(r) for r in rows],
                "scores": [_score_payload(s) for s in scores],
                "scored_share": len(scores) / max(len(rows), 1),
            }
        )

    @app.post("/v1/score")
    async def score(body: ScoreIn, request: Request, session: SessionDep, actor: ActorDep) -> dict[str, Any]:
        require_writer(actor)
        state = state_of(request)
        if state.model is None:
            raise HTTPException(status_code=503, detail="no served model on this server")
        forecasts = (await session.exec(select(Forecast))).all()
        scored_now = 0
        scored_forecasts = 0
        for f in forecasts:
            rows = (
                await session.exec(select(ForecastRow).where(ForecastRow.forecast_id == f.forecast_id))
            ).all()
            existing = {
                s.horizon
                for s in (await session.exec(select(Score).where(Score.forecast_id == f.forecast_id))).all()
            }
            added = 0
            for r in rows:
                if r.horizon in existing:
                    continue
                actual = state.model.actual(
                    f.authority,
                    r.target_hour.replace(tzinfo=UTC) if r.target_hour.tzinfo is None else r.target_hour,
                )
                if actual is None or actual <= 0:
                    continue
                session.add(_score_row(r, actual))
                added += 1
            if added:
                f.scored_rows = len(existing) + added
                f.scored_at = datetime.now(UTC)
                session.add(f)
                scored_forecasts += 1
            scored_now += added
        await session.flush()
        total_rows = sum(f.horizons for f in forecasts)
        scored_rows = sum(f.scored_rows for f in forecasts)
        unscored_share = 1.0 - scored_rows / total_rows if total_rows else 1.0
        await audit(
            session,
            actor,
            "score",
            "forecast",
            "",
            {
                "scored_rows": scored_now,
                "forecasts_touched": scored_forecasts,
                "unscored_share": unscored_share,
            },
        )
        return envelope(
            {
                "scored_rows": scored_now,
                "forecasts_touched": scored_forecasts,
                "forecasts": len(forecasts),
                "unscored_share": unscored_share,
            }
        )

    @app.get("/v1/scorecard")
    async def scorecard(session: SessionDep) -> dict[str, Any]:
        forecasts = (await session.exec(select(Forecast))).all()
        scores = (await session.exec(select(Score))).all()
        total_rows = sum(f.horizons for f in forecasts)
        by_authority: dict[str, list[float]] = {}
        f_by_id = {f.forecast_id: f for f in forecasts}
        for s in scores:
            by_authority.setdefault(f_by_id[s.forecast_id].authority, []).append(s.abs_pct_error)
        return envelope(
            {
                "forecasts": len(forecasts),
                "rows": total_rows,
                "scored_rows": len(scores),
                "unscored_share": 1.0 - len(scores) / total_rows if total_rows else 1.0,
                "mape": sum(s.abs_pct_error for s in scores) / len(scores) if scores else None,
                "coverage_90": sum(1 for s in scores if s.inside_90) / len(scores) if scores else None,
                "coverage_50": sum(1 for s in scores if s.inside_50) / len(scores) if scores else None,
                "by_authority": [
                    {"authority": a, "scored_rows": len(v), "mape": sum(v) / len(v)}
                    for a, v in sorted(by_authority.items())
                ],
            }
        )

    @app.get("/v1/audit")
    async def audit_log(session: SessionDep, limit: int = 100) -> dict[str, Any]:
        rows = (
            await session.exec(select(AuditEntry).order_by(col(AuditEntry.at).desc()).limit(min(limit, 500)))
        ).all()
        return envelope(
            {
                "entries": [
                    {
                        "at": r.at.isoformat(),
                        "actor": r.actor,
                        "action": r.action,
                        "resource": r.resource,
                        "resource_id": r.resource_id,
                        "detail": r.detail,
                    }
                    for r in rows
                ]
            }
        )

    return app


def _score_row(r: ForecastRow, actual: float) -> Score:
    q = {c: getattr(r, c) for c in QUANTILE_COLUMNS}
    pinball = {}
    for level, c in zip(QUANTILE_LEVELS, QUANTILE_COLUMNS, strict=True):
        diff = actual - q[c]
        pinball[f"pinball_{c}"] = level * diff if diff >= 0 else (level - 1) * diff
    return Score(
        forecast_id=r.forecast_id,
        horizon=r.horizon,
        target_hour=r.target_hour,
        actual=actual,
        abs_pct_error=abs(q["q50"] - actual) / actual,
        inside_50=q["q25"] <= actual <= q["q75"],
        inside_90=q["q05"] <= actual <= q["q95"],
        **pinball,
    )


def _forecast_payload(row: Forecast, issued: IssuedForecast | None = None) -> dict[str, Any]:
    payload = {
        "forecast_id": row.forecast_id,
        "authority": row.authority,
        "origin": row.origin.isoformat(),
        "model_version": row.model_version,
        "backend": row.backend,
        "spec_hash": row.spec_hash,
        "data_source": row.data_source,
        "horizons": row.horizons,
        "note": row.note,
        "issued_at": row.issued_at.isoformat(),
        "scored_at": row.scored_at.isoformat() if row.scored_at else None,
        "scored_rows": row.scored_rows,
    }
    if issued is not None:
        payload["rows"] = [
            {
                "horizon": h,
                "target_hour": t.isoformat(),
                **{c: float(issued.quantiles[i, k]) for k, c in enumerate(QUANTILE_COLUMNS)},
            }
            for i, (h, t) in enumerate(zip(issued.horizons, issued.target_hours, strict=True))
        ]
    return payload


def _row_payload(r: ForecastRow) -> dict[str, Any]:
    return {
        "horizon": r.horizon,
        "target_hour": r.target_hour.isoformat(),
        **{c: getattr(r, c) for c in QUANTILE_COLUMNS},
    }


def _score_payload(s: Score) -> dict[str, Any]:
    return {
        "horizon": s.horizon,
        "target_hour": s.target_hour.isoformat(),
        "actual": s.actual,
        "abs_pct_error": s.abs_pct_error,
        "inside_50": s.inside_50,
        "inside_90": s.inside_90,
        "scored_at": s.scored_at.isoformat(),
    }
