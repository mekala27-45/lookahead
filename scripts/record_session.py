"""Record an API session for the site's fallback bundle.

Starts the API in a child process against a local Postgres (or drives a running server with
--base-url), walks the flow the site performs (health, the authorities, one forecast issued per
authority, the scoring pass, the scorecard, each forecast read back, the model list and the
audit log) and writes every response, labelled recorded, to web/public/data/recorded_session.json.
When the live API is asleep the site serves these responses and says so on the page. Every
forecast the recording issues carries the note the reset step deletes by.

    LOOKAHEAD_TEST_DATABASE_URL=postgresql+psycopg://... python scripts/record_session.py --start-server
    python scripts/record_session.py --base-url https://lookahead-grid-api.fly.dev --token ...
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "public" / "data" / "recorded_session.json"
NOTE = "recorded session for the control room"


def wait_for(base: str, seconds: float = 120.0) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if httpx.get(f"{base}/v1/health", timeout=5.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise SystemExit(f"the API at {base} did not answer within {seconds:.0f} seconds")


def record(base: str, token: str, limit: int | None) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"}
    session: dict[str, Any] = {
        "recorded": True,
        "recorded_at": datetime.now(UTC).isoformat(),
        "base_url": base,
        "note": NOTE,
        "responses": {},
    }
    responses: dict[str, Any] = session["responses"]

    def get(name: str, path: str) -> dict[str, Any]:
        r = httpx.get(f"{base}{path}", timeout=120.0)
        body = r.json()
        responses[name] = {"method": "GET", "path": path, "status": r.status_code, "body": body}
        return dict(body)

    def post(name: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        r = httpx.post(f"{base}{path}", json=payload, headers=headers, timeout=180.0)
        body = r.json()
        responses[name] = {
            "method": "POST",
            "path": path,
            "status": r.status_code,
            "request": payload,
            "body": body,
        }
        if r.status_code >= 400:
            raise SystemExit(f"{path} answered {r.status_code}: {body}")
        return dict(body)

    get("health", "/v1/health")
    authorities = [a["authority"] for a in get("authorities", "/v1/authorities")["authorities"]]
    if limit:
        authorities = authorities[:limit]
    issued: dict[str, str] = {}
    for authority in authorities:
        body = post(f"issue_{authority}", "/v1/forecasts", {"authority": authority, "note": NOTE})
        issued[authority] = str(body["forecast_id"])
    post("score", "/v1/score", {"note": NOTE})
    get("scorecard", "/v1/scorecard")
    for authority, forecast_id in issued.items():
        get(f"forecast_{authority}", f"/v1/forecasts/{forecast_id}")
    # The issued responses carry their rows back too, so the site can draw the fan from either.
    for authority in issued:
        full = responses[f"forecast_{authority}"]["body"]
        responses[f"issue_{authority}"]["body"]["rows"] = full.get("rows", [])
        responses[f"issue_{authority}"]["body"]["scores"] = full.get("scores", [])
        responses[f"issue_{authority}"]["body"]["scored_share"] = full.get("scored_share", 0.0)
    get("forecasts", "/v1/forecasts?limit=100")
    get("models", "/v1/models")
    get("audit", "/v1/audit?limit=50")
    session["issued"] = issued
    return session


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--start-server", action="store_true")
    parser.add_argument("--port", type=int, default=8793)
    parser.add_argument("--token", default=os.environ.get("LOOKAHEAD_WRITE_TOKEN", "record-token"))
    parser.add_argument("--limit", type=int, default=None, help="record only the first N authorities")
    args = parser.parse_args()
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
                "LOOKAHEAD_WRITE_TOKEN": args.token,
                "LOOKAHEAD_ENV": "recording",
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
        session = record(base, args.token, args.limit)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(session, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"recorded {len(session['responses'])} responses from {base} to {OUT.relative_to(ROOT)}")
        return 0
    finally:
        if server is not None:
            server.terminate()
            server.wait(timeout=20)


if __name__ == "__main__":
    sys.exit(main())
