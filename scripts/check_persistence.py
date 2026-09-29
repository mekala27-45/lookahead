"""The out of process check: issue a forecast, score it against the actuals the server holds, and
read the rows back through a connection this process opens itself.

Two modes. `--start-server` migrates with alembic, starts the API in a child process against
the database URL, drives it over HTTP, then reads the forecast, its rows, its scores and the
audit row with a fresh psycopg connection in this process. `--base-url` drives a live server
(the Fly deployment) and reads back through the API's own GET endpoints from this separate
client, which is the verification the README prints. In both modes the audit row must be
observed at or before the response's served_at.

    python scripts/check_persistence.py --start-server
    python scripts/check_persistence.py --base-url https://lookahead-grid-api.fly.dev
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from lookahead_core.statements import STATEMENT

NOTE = "persistence check"


def wait_for(base: str, seconds: float = 90.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/v1/health", timeout=5.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise SystemExit(f"the API at {base} did not answer within {seconds:.0f} seconds")


def drive(base: str, token: str, authority: str | None) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"}
    if authority is None:
        listed = httpx.get(f"{base}/v1/authorities", timeout=60.0)
        listed.raise_for_status()
        authorities = listed.json()["authorities"]
        if not authorities:
            raise SystemExit("the server serves no authorities")
        authority = str(authorities[0]["authority"])
    issued = httpx.post(
        f"{base}/v1/forecasts", json={"authority": authority, "note": NOTE}, headers=headers, timeout=120.0
    )
    issued.raise_for_status()
    body = issued.json()
    if body["statement"] != STATEMENT:
        raise SystemExit("the forecast response is missing the statement")
    scored = httpx.post(f"{base}/v1/score", json={"note": NOTE}, headers=headers, timeout=120.0)
    scored.raise_for_status()
    return {
        "forecast_id": str(body["forecast_id"]),
        "authority": authority,
        "origin": str(body["origin"]),
        "model_version": str(body["model_version"]),
        "served_at": datetime.fromisoformat(str(body["served_at"])),
        "scored_rows_reported": int(scored.json()["scored_rows"]),
        "unscored_share": float(scored.json()["unscored_share"]),
    }


def read_back_via_api(base: str, ids: dict[str, object]) -> dict[str, object]:
    forecast = httpx.get(f"{base}/v1/forecasts/{ids['forecast_id']}", timeout=60.0)
    forecast.raise_for_status()
    audit = httpx.get(f"{base}/v1/audit?limit=50", timeout=60.0)
    audit.raise_for_status()
    f = forecast.json()
    if f["statement"] != STATEMENT or audit.json()["statement"] != STATEMENT:
        raise SystemExit("a response is missing the statement")
    if f["authority"] != ids["authority"] or len(f["rows"]) != 48:
        raise SystemExit("the forecast did not come back with its 48 rows")
    if not f["scores"]:
        raise SystemExit("the forecast has no scores after scoring")
    entries = audit.json()["entries"]
    issue = [x for x in entries if x["action"] == "issue" and x["resource_id"] == ids["forecast_id"]]
    if not issue:
        raise SystemExit("no audit row for the issued forecast")
    at = datetime.fromisoformat(issue[0]["at"])
    if at > ids["served_at"]:  # type: ignore[operator]
        raise SystemExit("the audit row was written after the response was served")
    return {
        "forecast": {"authority": f["authority"], "rows": len(f["rows"]), "scores": len(f["scores"])},
        "scored_share": f["scored_share"],
        "audit_entries": len(entries),
        "audit_before_response": True,
    }


def read_back_via_postgres(url: str, ids: dict[str, object]) -> dict[str, object]:
    import psycopg

    plain = url.replace("postgresql+psycopg://", "postgresql://")
    with psycopg.connect(plain) as conn, conn.cursor() as cur:
        cur.execute(
            "select authority, model_version from forecasts where forecast_id = %s", (ids["forecast_id"],)
        )
        forecast = cur.fetchone()
        cur.execute("select count(*) from forecast_rows where forecast_id = %s", (ids["forecast_id"],))
        n_rows = cur.fetchone()
        cur.execute(
            "select count(*), avg(abs_pct_error) from scores where forecast_id = %s", (ids["forecast_id"],)
        )
        scores = cur.fetchone()
        cur.execute(
            "select at from audit_log where action = 'issue' and resource_id = %s", (ids["forecast_id"],)
        )
        audit = cur.fetchone()
    if forecast is None or forecast[0] != ids["authority"] or forecast[1] != ids["model_version"]:
        raise SystemExit("the forecast row is missing from a fresh connection")
    if n_rows is None or n_rows[0] != 48:
        raise SystemExit("the 48 forecast rows are missing from a fresh connection")
    if scores is None or scores[0] == 0 or scores[0] != ids["scored_rows_reported"]:
        raise SystemExit("the score rows are missing or do not match what the server reported")
    if audit is None or audit[0] > ids["served_at"]:
        raise SystemExit("the audit row is missing or later than the response")
    return {
        "forecast": True,
        "rows": int(n_rows[0]),
        "scores": int(scores[0]),
        "mape_of_check": float(scores[1]),
        "audit_before_response": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--start-server", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--authority", default=None)
    parser.add_argument("--out", default=None, help="write the observation as JSON here as well")
    args = parser.parse_args()
    token = os.environ.get("LOOKAHEAD_WRITE_TOKEN", "check-token")
    server: subprocess.Popen[bytes] | None = None
    base = args.base_url
    try:
        if args.start_server:
            url = os.environ.get("LOOKAHEAD_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
            if not url:
                raise SystemExit("set LOOKAHEAD_TEST_DATABASE_URL or DATABASE_URL to start a server")
            env = {
                **os.environ,
                "DATABASE_URL": url,
                "LOOKAHEAD_WRITE_TOKEN": token,
                "LOOKAHEAD_ENV": "check",
            }
            subprocess.run(
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
                check=True,
            )
            server = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "lookahead_api.main:app",
                    "--port",
                    str(args.port),
                    "--log-level",
                    "warning",
                ],
                cwd=ROOT,
                env=env,
            )
            base = f"http://127.0.0.1:{args.port}"
        if not base:
            raise SystemExit("give --base-url or --start-server")
        wait_for(base)
        ids = drive(base, token, args.authority)
        if args.start_server:
            url = os.environ.get("LOOKAHEAD_TEST_DATABASE_URL") or os.environ["DATABASE_URL"]
            observed = read_back_via_postgres(url, ids)
        else:
            observed = read_back_via_api(base, ids)
        report = {"base_url": base, "ids": {k: str(v) for k, v in ids.items()}, "observed": observed}
        print(json.dumps(report, indent=1))
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
        print(
            "persistence check: a forecast, its rows and its scores were read back from outside the server process"
        )
        return 0
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=20)


if __name__ == "__main__":
    sys.exit(main())
