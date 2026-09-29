"""Stage: latency as measured by scripts/load_test.py, recorded into the manifest.

Reads results/latency/local.json and results/latency/live.json when they exist, plus the
backtest's batch throughput, and writes results/manifests/latency.json.
"""

from __future__ import annotations

import json

from lookahead_core.manifest import Manifest, Scribe
from lookahead_core.paths import Paths


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    manifest = Manifest(as_of=as_of, seed=seed)
    folder = paths.results / "latency"
    found = 0
    for label in ("local", "live"):
        path = folder / f"{label}.json"
        w = Scribe(
            manifest,
            source="recorded",
            model="none",
            population=f"the {label} API under scripts/load_test.py",
            origin="scripts/load_test.py",
        )
        if not path.exists():
            w.put(f"latency.{label}.status", "not measured", "text")
            continue
        found += 1
        seen = json.loads(path.read_text(encoding="utf-8"))
        w.put(f"latency.{label}.status", "measured", "text")
        w.put(f"latency.{label}.base_url", str(seen["base_url"]), "text")
        w.put(f"latency.{label}.measured_at", str(seen["measured_at"]), "text")
        w.put(f"latency.{label}.requests", int(seen["requests"]), "int")
        w.put(f"latency.{label}.concurrency", int(seen["concurrency"]), "int")
        w.put(f"latency.{label}.first_request_ms", float(seen["first_request_ms"]), "ms")
        for kind in ("issue", "read"):
            for stat in ("p50_ms", "p99_ms", "max_ms"):
                w.put(f"latency.{label}.{kind}.{stat}", float(seen[kind][stat]), "ms")
        w.put(f"latency.{label}.burst_issue_max_ms", float(seen["burst_issue_max_ms"]), "ms")
    w = Scribe(
        manifest,
        source="recorded",
        model="none",
        population="the load test files found",
        origin="lookahead_registry.stages.latency",
    )
    w.put("latency.measurements", found, "int")
    manifest.save(paths.results / "manifests" / "latency.json")
    return manifest
