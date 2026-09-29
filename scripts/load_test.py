"""Latency of the forecast log from a stated load: p50 and p99 of POST /v1/forecasts and of
GET /v1/forecasts/{id} over N sequential requests plus a burst of concurrent issues, against a
running server. Writes results/latency/<label>.json, which the registry's latency gate reads and
the documents quote.

    python scripts/load_test.py --base-url http://127.0.0.1:8080 --label local --requests 60 --concurrency 8
    python scripts/load_test.py --base-url https://lookahead-grid-api.fly.dev --label live
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
NOTE = "load test"


async def _issue(
    client: httpx.AsyncClient, base: str, authority: str, headers: dict[str, str]
) -> tuple[float, str]:
    started = time.perf_counter()
    response = await client.post(
        f"{base}/v1/forecasts", json={"authority": authority, "note": NOTE}, headers=headers, timeout=120.0
    )
    response.raise_for_status()
    return (time.perf_counter() - started) * 1000.0, str(response.json()["forecast_id"])


async def _read(client: httpx.AsyncClient, base: str, forecast_id: str) -> float:
    started = time.perf_counter()
    response = await client.get(f"{base}/v1/forecasts/{forecast_id}", timeout=60.0)
    response.raise_for_status()
    return (time.perf_counter() - started) * 1000.0


def _summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    n = len(ordered)
    if n == 0:
        return {"p50_ms": float("nan"), "p99_ms": float("nan"), "max_ms": float("nan")}
    p99_index = min(n - 1, max(0, int(round(0.99 * (n - 1)))))
    return {
        "p50_ms": round(statistics.median(ordered), 1),
        "p99_ms": round(ordered[p99_index], 1),
        "max_ms": round(ordered[-1], 1),
        "mean_ms": round(statistics.fmean(ordered), 1),
    }


async def run(base: str, token: str, requests: int, concurrency: int) -> dict[str, object]:
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        health = await client.get(f"{base}/v1/health", timeout=60.0)
        health.raise_for_status()
        authorities = [
            a["authority"]
            for a in (await client.get(f"{base}/v1/authorities", timeout=60.0)).json()["authorities"]
        ]
        if not authorities:
            raise SystemExit("the server serves no authorities")
        # The first request may wake the machine; it is timed separately and not counted.
        wake_ms, _ = await _issue(client, base, authorities[0], headers)
        issues: list[float] = []
        ids: list[str] = []
        for i in range(requests):
            ms, forecast_id = await _issue(client, base, authorities[i % len(authorities)], headers)
            issues.append(ms)
            ids.append(forecast_id)
        reads = [await _read(client, base, forecast_id) for forecast_id in ids]
        burst = await asyncio.gather(
            *[_issue(client, base, authorities[i % len(authorities)], headers) for i in range(concurrency)]
        )
    return {
        "base_url": base,
        "measured_at": datetime.now(UTC).isoformat(),
        "requests": requests,
        "concurrency": concurrency,
        "authorities": len(authorities),
        "first_request_ms": round(wake_ms, 1),
        "issue": _summary(issues),
        "read": _summary(reads),
        "burst_issue_max_ms": round(max(ms for ms, _ in burst), 1),
        "errors": 0,
        "note": "sequential requests after one warming request; the burst is concurrent issues",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--label", default="local", help="file name under results/latency")
    parser.add_argument("--requests", type=int, default=60)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--token", default=os.environ.get("LOOKAHEAD_WRITE_TOKEN", "check-token"))
    args = parser.parse_args()
    result = asyncio.run(run(args.base_url.rstrip("/"), args.token, args.requests, args.concurrency))
    out = ROOT / "results" / "latency" / f"{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
