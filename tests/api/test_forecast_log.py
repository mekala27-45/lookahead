"""The forecast log, observed from outside the application's session."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lookahead_api.app import create_app
from lookahead_core.statements import STATEMENT

from tests.api.conftest import TOKEN, plain_url, rows

pytestmark = pytest.mark.postgres


def _first_authority(client: TestClient) -> str:
    listed = client.get("/v1/authorities").json()["authorities"]
    assert listed, "the served model has no authorities"
    return str(listed[0]["authority"])


def test_forecast_is_committed(client: TestClient, auth: dict[str, str], clean_db: str) -> None:
    authority = _first_authority(client)
    response = client.post("/v1/forecasts", json={"authority": authority, "note": "test"}, headers=auth)
    assert response.status_code == 201, response.text
    body = response.json()
    forecast_id = body["forecast_id"]
    assert body["stored_rows"] == 48
    stored = rows(
        clean_db,
        "select authority, horizons, model_version from forecasts where forecast_id = %s",
        (forecast_id,),
    )
    assert stored == [(authority, 48, body["model_version"])]
    stored_rows = rows(
        clean_db,
        "select horizon, q05, q50, q95 from forecast_rows where forecast_id = %s order by horizon",
        (forecast_id,),
    )
    assert [r[0] for r in stored_rows] == list(range(1, 49))
    assert all(r[1] <= r[2] <= r[3] for r in stored_rows), "quantiles are stored in order"
    assert all(r[2] > 0 for r in stored_rows), "the median is megawatts, positive"


def test_scores_are_committed(client: TestClient, auth: dict[str, str], clean_db: str) -> None:
    authority = _first_authority(client)
    issued = client.post("/v1/forecasts", json={"authority": authority}, headers=auth).json()
    scored = client.post("/v1/score", json={"note": "test"}, headers=auth)
    assert scored.status_code == 200, scored.text
    body = scored.json()
    assert body["forecasts"] == 1
    stored = rows(
        clean_db,
        "select count(*), min(actual), max(abs_pct_error) from scores where forecast_id = %s",
        (issued["forecast_id"],),
    )
    count, min_actual, max_ape = stored[0]
    assert count == body["scored_rows"]
    assert count > 0, "the bundle holds actuals for the latest origin's target hours"
    assert min_actual > 0
    assert 0 <= max_ape < 1.0
    flagged = rows(
        clean_db,
        "select scored_rows, scored_at from forecasts where forecast_id = %s",
        (issued["forecast_id"],),
    )
    assert flagged[0][0] == count and flagged[0][1] is not None
    again = client.post("/v1/score", json={}, headers=auth).json()
    assert again["scored_rows"] == 0, "scoring is idempotent: nothing is scored twice"
    assert abs(again["unscored_share"] - (1 - count / 48)) < 1e-9


def test_audit_precedes_response(client: TestClient, auth: dict[str, str], clean_db: str) -> None:
    authority = _first_authority(client)
    response = client.post("/v1/forecasts", json={"authority": authority}, headers=auth)
    served_at = datetime.fromisoformat(response.json()["served_at"])
    audit = rows(clean_db, "select at, action, resource_id, actor from audit_log order by at")
    assert len(audit) == 1
    at, action, resource_id, actor = audit[0]
    assert action == "issue" and resource_id == response.json()["forecast_id"] and actor == "token"
    assert at <= served_at
    client.post("/v1/score", json={}, headers=auth)
    audit = rows(clean_db, "select action from audit_log order by at")
    assert [a[0] for a in audit] == ["issue", "score"]


def test_writes_need_the_token(client: TestClient, clean_db: str) -> None:
    authority = _first_authority(client)
    assert client.post("/v1/forecasts", json={"authority": authority}).status_code == 401
    assert client.post("/v1/score", json={}).status_code == 401
    wrong = client.post(
        "/v1/forecasts", json={"authority": authority}, headers={"Authorization": "Bearer wrong"}
    )
    assert wrong.status_code == 401
    assert rows(clean_db, "select count(*) from forecasts")[0][0] == 0
    assert rows(clean_db, "select count(*) from audit_log")[0][0] == 0, "a refused write leaves no audit row"


def test_unknown_authority_and_forecast(client: TestClient, auth: dict[str, str]) -> None:
    assert client.post("/v1/forecasts", json={"authority": "NOPE"}, headers=auth).status_code == 404
    missing = client.get("/v1/forecasts/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["statement"] == STATEMENT


def test_forecast_reads_back_with_its_scores(client: TestClient, auth: dict[str, str]) -> None:
    authority = _first_authority(client)
    issued = client.post("/v1/forecasts", json={"authority": authority}, headers=auth).json()
    client.post("/v1/score", json={}, headers=auth)
    got = client.get(f"/v1/forecasts/{issued['forecast_id']}").json()
    assert got["authority"] == authority
    assert len(got["rows"]) == 48
    assert got["rows"][0]["horizon"] == 1
    assert len(got["scores"]) == got["scored_rows"] > 0
    assert abs(got["scored_share"] - got["scored_rows"] / 48) < 1e-9
    listed = client.get(f"/v1/forecasts?authority={authority}").json()["forecasts"]
    assert [f["forecast_id"] for f in listed] == [issued["forecast_id"]]
    card = client.get("/v1/scorecard").json()
    assert card["forecasts"] == 1 and card["scored_rows"] == got["scored_rows"]
    assert card["mape"] is not None and 0 <= card["mape"] < 1


def test_statement_on_every_endpoint(client: TestClient, auth: dict[str, str]) -> None:
    """Every route in the app's route table answers with the statement, walked from the table so
    a new route cannot be added without it."""
    authority = _first_authority(client)
    issued = client.post("/v1/forecasts", json={"authority": authority}, headers=auth).json()
    fill = {"forecast_id": issued["forecast_id"]}
    seen = 0
    for route in client.app.routes:  # type: ignore[attr-defined]
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None) or set()
        if not path.startswith("/v1/"):
            continue
        for method in methods:
            if method not in {"GET", "POST"}:
                continue
            concrete = path.format(**fill)
            if method == "GET":
                response = client.get(concrete)
            else:
                body = {"authority": authority} if concrete == "/v1/forecasts" else {}
                response = client.post(concrete, json=body, headers=auth)
            assert response.status_code < 500, f"{method} {concrete}: {response.text}"
            assert response.json()["statement"] == STATEMENT, f"{method} {concrete} lacks the statement"
            seen += 1
    assert seen >= 9
    assert client.get("/v1/forecasts/nothing").json()["statement"] == STATEMENT
    assert client.post("/v1/forecasts", json={"authority": ""}, headers=auth).json()["statement"] == STATEMENT


def test_health_models_and_authorities(client: TestClient) -> None:
    health = client.get("/v1/health").json()
    assert health["status"] == "ok" and health["database"] == "ok"
    assert health["backend"] in {"own", "gbm"} and health["authorities"] > 0
    models = client.get("/v1/models").json()
    assert models["serving"] == health["model_version"]
    authorities = client.get("/v1/authorities").json()["authorities"]
    assert all(a["latest_origin"].endswith("+00:00") for a in authorities)
    assert all(a["latest_origin"][11:16] == "00:00" for a in authorities), "origins are issued at 00:00 UTC"


def test_schema_setting_keeps_the_tables_apart(database_url: str, results: Path) -> None:
    """With LOOKAHEAD_DB_SCHEMA the tables live in that schema, so the API can share the one
    free Neon database with another project's tables without touching them."""
    import psycopg
    from lookahead_api.db import Forecast, SQLModel, ensure_schema, make_engine
    from lookahead_api.settings import Settings

    schema = "lookahead_schema_test"
    ensure_schema(database_url, schema)
    engine = make_engine(database_url, schema)
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    engine.dispose()
    settings = Settings(
        database_url=database_url, write_token=TOKEN, results=results, environment="test", schema=schema
    )
    with TestClient(create_app(settings)) as client:
        authority = _first_authority(client)
        issued = client.post(
            "/v1/forecasts", json={"authority": authority}, headers={"Authorization": f"Bearer {TOKEN}"}
        )
        assert issued.status_code == 201, issued.text
    with psycopg.connect(plain_url(database_url)) as conn, conn.cursor() as cur:
        cur.execute(f"select count(*) from {schema}.forecasts")
        assert cur.fetchone() == (1,)
    # The hosted database's proxy drops the `options` startup parameter, so the schema must be in
    # the SQL itself: a connection whose search path does not name the schema still finds the rows.
    from sqlalchemy import text
    from sqlmodel import Session, select

    engine = make_engine(database_url, schema)
    with Session(engine) as session:
        session.exec(text("set search_path to public"))  # type: ignore[call-overload]
        found = session.exec(select(Forecast)).all()
        assert [f.forecast_id for f in found] == [issued.json()["forecast_id"]]
    engine.dispose()
    with psycopg.connect(plain_url(database_url)) as conn, conn.cursor() as cur:
        cur.execute(
            "select table_schema from information_schema.tables where table_name = 'forecasts' order by 1"
        )
        schemas = [r[0] for r in cur.fetchall()]
    assert schema in schemas
