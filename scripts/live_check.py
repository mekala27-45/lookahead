"""The live check: the Pages site and the Fly API opened in a real browser after the deploy.

The check itself is done in a browser on a machine that can reach both hosts (the build sandbox
cannot): every route loaded, the statement read on each, one forecast issued through the site
with its id shown, and the recorded session verified with the API asleep (the machine stopped
after its idle timeout, so the site's first probe meets the wake up). This script writes what
was seen to results/live_check.json in the shape the claim gate reads; it refuses a report that
names no browser, no routes or no forecast id.

    uv run python scripts/live_check.py --observations results/scratch/live_observations.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "live_check.json"
REQUIRED_ROUTES = ("/", "/forecast/", "/backtest/", "/hierarchy/", "/events/", "/households/", "/report/")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observations", required=True, help="JSON written from the browser session")
    args = parser.parse_args()
    seen = json.loads(Path(args.observations).read_text(encoding="utf-8"))
    routes = seen.get("routes", [])
    if not seen.get("browser"):
        raise SystemExit("the observations name no browser")
    missing = [r for r in REQUIRED_ROUTES if not any(str(x.get("route", "")).startswith(r) for x in routes)]
    if missing:
        raise SystemExit(f"routes not checked: {missing}")
    if not seen.get("forecast_id"):
        raise SystemExit("no forecast was issued through the site")
    loaded = sum(1 for r in routes if r.get("loaded"))
    statements = sum(1 for r in routes if r.get("statement"))
    passed = (
        loaded == len(routes)
        and statements == len(routes)
        and bool(seen.get("forecast_id"))
        and bool(seen.get("asleep_recorded_session_shown"))
        and str(seen.get("api_health_status", "")) == "ok"
    )
    report = {
        "checked_at": seen.get("checked_at") or datetime.now(UTC).isoformat(),
        "browser": seen["browser"],
        "site_url": seen.get("site_url", ""),
        "api_url": seen.get("api_url", ""),
        "routes": routes,
        "routes_total": len(routes),
        "routes_loaded": loaded,
        "statements_present": statements,
        "api_health_status": seen.get("api_health_status", ""),
        "api_model_version": seen.get("api_model_version", ""),
        "forecast_id": seen["forecast_id"],
        "forecast_source": seen.get("forecast_source", ""),
        "first_probe_status": seen.get("first_probe_status", ""),
        "asleep_recorded_session_shown": bool(seen.get("asleep_recorded_session_shown")),
        "asleep_note": seen.get("asleep_note", ""),
        "passed": passed,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
