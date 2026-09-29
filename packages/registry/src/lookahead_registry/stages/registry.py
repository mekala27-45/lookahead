"""Stage: the registry. Every candidate backend through the seven gates; the served model chosen.

Reads what the earlier stages measured: the backtest scoring frames (MAPE against the seasonal
naive per authority at horizons 1 to 24, the peak timing median), the skill table (verdicts
after correction), the backends' validation coverage (from the exports' calibration, measured
here on the validation year), the hierarchy's coherence gaps, the latest latency measurement
(local or live), and the leakage check run now on one authority's real series. Writes
results/registry/gates.json, results/registry/served.json and results/manifests/registry.json.
The API reads served.json to choose which export to load.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

import numpy as np
import polars as pl
from lookahead_core.config import POLICY
from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths
from lookahead_evaluation.metrics import row_errors
from lookahead_features.build import FeatureSpec
from lookahead_features.leakage import recomputation_check
from lookahead_forecast.interface import PanelData

from lookahead_registry.gates import (
    GATE_NAMES,
    GateResult,
    all_passed,
    choose_served,
    gate_coherence_exact,
    gate_coverage_90_on_validation,
    gate_leakage_check_green,
    gate_mape_not_worse_than_naive,
    gate_p99_latency,
    gate_peak_timing_median,
    gate_skill_not_significantly_negative,
)
from lookahead_registry.stages.backtest import load_data

CANDIDATES = ("own", "gbm")


def _per_authority_vs_naive(scoring: pl.DataFrame) -> dict[str, tuple[float, float]]:
    errors = row_errors(scoring.filter(pl.col("horizon") <= 24)).filter(
        pl.col("ape_naive").is_not_null() & pl.col("ape_naive").is_not_nan()
    )
    table = errors.group_by("authority").agg(
        pl.col("ape_model").mean().alias("model"), pl.col("ape_naive").mean().alias("naive")
    )
    return {str(r["authority"]): (float(r["model"]), float(r["naive"])) for r in table.iter_rows(named=True)}


def _verdicts(paths: Paths, backend: str) -> dict[str, str]:
    path = paths.results / "skill" / "skill_rows.parquet"
    if not path.exists():
        return {}
    rows = pl.read_parquet(path).filter((pl.col("backend") == backend) & (pl.col("band") == "h1_24"))
    return {str(r["authority"]): str(r["verdict"]) for r in rows.iter_rows(named=True)}


def _validation_coverage(paths: Paths, backend: str) -> float | None:
    """The 90 percent coverage on the validation year, recorded by the backtest stage."""
    path = paths.results / "manifests" / f"backtest_{backend}.json"
    if not path.exists():
        return None
    values = json.loads(path.read_text(encoding="utf-8")).get("values", {})
    entry = values.get(f"backtest.{backend}.validation_coverage_90")
    if entry is None:
        return None
    return float(entry["value"])


def _peak_timing_median(paths: Paths, backend: str) -> float | None:
    path = paths.results / "manifests" / f"backtest_{backend}.json"
    if not path.exists():
        return None
    values = json.loads(path.read_text(encoding="utf-8")).get("values", {})
    entry = values.get(f"backtest.{backend}.peaks.model_timing_median")
    return float(entry["value"]) if entry else None


def _coherence_gaps(paths: Paths) -> dict[str, float]:
    path = paths.results / "manifests" / "hierarchy.json"
    if not path.exists():
        return {}
    values = json.loads(path.read_text(encoding="utf-8")).get("values", {})
    gaps = {}
    for method in ("bottom_up", "top_down", "mint"):
        entry = values.get(f"hierarchy.coherence_gap_mw.{method}")
        if entry is not None:
            gaps[method] = float(entry["value"])
    return gaps


def _latency(paths: Paths) -> tuple[float | None, str]:
    folder = paths.results / "latency"
    for label in ("live", "local"):
        path = folder / f"{label}.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            return float(payload["issue"]["p99_ms"]), f"{label}, {payload['requests']} requests"
    return None, ""


def _leakage(data: PanelData, seed: int) -> GateResult:
    authority = data.names[0]
    a = data.authorities[authority]
    origins = data.origins(data.validation_start, data.test_start, authority)[:40]
    report = recomputation_check(
        a.series, a.temperature, a.humidity, a.offsets, FeatureSpec(), a.typical_mw, origins, seed
    )
    result = gate_leakage_check_green(report.rows_checked, report.max_abs_gap, report.leaky_lag_refused)
    return GateResult(
        name=result.name,
        passed=result.passed,
        value=result.value,
        threshold=result.threshold,
        evidence=f"{authority}: " + result.evidence,
    )


def _headline(paths: Paths, backend: str) -> float:
    """Wins minus losses against the operator at horizons 1 to 24, the number the README leads with."""
    path = paths.results / "manifests" / "skill.json"
    if not path.exists():
        return float("-inf")
    values = json.loads(path.read_text(encoding="utf-8")).get("values", {})
    wins = values.get(f"skill.{backend}.h1_24.wins", {}).get("value")
    losses = values.get(f"skill.{backend}.h1_24.losses", {}).get("value")
    if wins is None or losses is None:
        return float("-inf")
    return float(wins) - float(losses)


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    started = time.time()
    folder = paths.results / "registry"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(as_of=as_of, seed=seed)
    data = load_data(paths)
    leakage = _leakage(data, seed)
    gaps = _coherence_gaps(paths)
    p99, where = _latency(paths)
    models: list[dict[str, Any]] = []
    candidates: dict[str, tuple[list[GateResult], float]] = {}
    for backend in CANDIDATES:
        export = paths.results / "models" / f"{backend}_model.json"
        scoring_path = paths.results / "backtest" / backend / "scoring.parquet"
        if not export.exists() or not scoring_path.exists():
            models.append(
                {
                    "backend": backend,
                    "version": None,
                    "spec_hash": None,
                    "served": False,
                    "ran": False,
                    "gates": {},
                    "reason": "no backtest and export for this backend",
                }
            )
            continue
        payload = json.loads(export.read_text(encoding="utf-8"))
        scoring = pl.read_parquet(scoring_path)
        results = [
            gate_mape_not_worse_than_naive(_per_authority_vs_naive(scoring)),
            _skill_gate(_verdicts(paths, backend)),
            _coverage_gate(_validation_coverage(paths, backend)),
            _peak_gate(_peak_timing_median(paths, backend)),
            _coherence_gate(gaps),
            _latency_gate(p99, where),
            leakage,
        ]
        assert [r.name for r in results] == list(GATE_NAMES)
        candidates[backend] = (results, _headline(paths, backend))
        models.append(
            {
                "backend": backend,
                "version": payload["version"],
                "spec_hash": payload["spec_hash"],
                "served": False,
                "ran": True,
                "gates": {r.name: r.as_dict() for r in results},
                "passed": all_passed(results),
                "headline_wins_minus_losses": candidates[backend][1],
            }
        )
    served, reason = choose_served(candidates) if candidates else (None, "no backend has run")
    for m in models:
        m["served"] = m["backend"] == served
    gates_payload = {
        "chosen_at": datetime.now(UTC).isoformat(),
        "as_of": as_of,
        "served": served,
        "reason": reason,
        "gates": list(GATE_NAMES),
        "models": models,
    }
    (folder / "gates.json").write_text(json.dumps(gates_payload, indent=1) + "\n", encoding="utf-8")
    served_payload = {
        "backend": served or "own",
        "served_by_gates": served is not None,
        "reason": reason,
        "version": next((m["version"] for m in models if m["backend"] == (served or "own")), None),
        "chosen_at": datetime.now(UTC).isoformat(),
    }
    (folder / "served.json").write_text(json.dumps(served_payload, indent=1) + "\n", encoding="utf-8")

    w = Scribe(
        manifest,
        source="real:eia930",
        model="both",
        population="the candidate backends over the test year",
        origin="lookahead_registry.stages.registry",
    )
    w.put("registry.gates", len(GATE_NAMES), "int")
    w.put("registry.candidates", len(candidates), "int")
    w.put("registry.served", served or "none", "text")
    w.put("registry.served_reason", reason, "text")
    w.put("registry.fallback_backend", "own", "text")
    rows: list[list[Scalar]] = []
    for m in models:
        for name in GATE_NAMES:
            g = m["gates"].get(name)
            if g is None:
                rows.append([m["backend"], name, "not run", None, "not run", "the backend has not run"])
                continue
            rows.append(
                [
                    m["backend"],
                    name,
                    "pass" if g["passed"] else "fail",
                    float(g["value"]) if isinstance(g["value"], int | float) else None,
                    str(g["threshold"]),
                    g["evidence"],
                ]
            )
            w.put(f"registry.{m['backend']}.{name}", "pass" if g["passed"] else "fail", "text")
            if isinstance(g["value"], int | float) and np.isfinite(float(g["value"])):
                w.put(f"registry.{m['backend']}.{name}.value", float(g["value"]), "float4")
        if m.get("ran"):
            w.put(f"registry.{m['backend']}.passed", "yes" if m["passed"] else "no", "text")
            w.put(f"registry.{m['backend']}.version", str(m["version"]), "text")
            w.put(
                f"registry.{m['backend']}.gates_passed",
                sum(1 for g in m["gates"].values() if g["passed"]),
                "int",
            )
    w.table(
        "registry.gates",
        ["Backend", "Gate", "Result", "Value", "Threshold", "Evidence"],
        ["text", "text", "text", "float4", "text", "text"],
        rows,
    )
    w.put("registry.latency_source", where or "not yet measured", "text")
    w.put("registry.seconds", time.time() - started, "float1")
    manifest.save(paths.results / "manifests" / "registry.json")
    return manifest


def _skill_gate(verdicts: dict[str, str]) -> GateResult:
    if not verdicts:
        return GateResult(
            "skill_not_significantly_negative",
            False,
            "not measured",
            POLICY.max_share_significantly_worse_than_operator,
            "the skill stage has not run for this backend",
        )
    return gate_skill_not_significantly_negative(verdicts)


def _coverage_gate(coverage: float | None) -> GateResult:
    if coverage is None:
        return GateResult(
            "coverage_90_on_validation",
            False,
            "not measured",
            f"{POLICY.coverage_band_90[0]:.2f} to {POLICY.coverage_band_90[1]:.2f}",
            "no validation coverage recorded",
        )
    return gate_coverage_90_on_validation(coverage)


def _peak_gate(median: float | None) -> GateResult:
    if median is None:
        return GateResult(
            "peak_timing_median",
            False,
            "not measured",
            POLICY.max_median_peak_timing_error_hours,
            "no peak timing error recorded",
        )
    return gate_peak_timing_median(median)


def _coherence_gate(gaps: dict[str, float]) -> GateResult:
    if not gaps:
        return GateResult("coherence_exact", False, "not measured", 1e-3, "the hierarchy stage has not run")
    return gate_coherence_exact(gaps)


def _latency_gate(p99: float | None, where: str) -> GateResult:
    if p99 is None:
        return GateResult(
            "p99_latency", False, "not measured", POLICY.max_p99_latency_ms, "no load test has run"
        )
    return gate_p99_latency(p99, where=where)
