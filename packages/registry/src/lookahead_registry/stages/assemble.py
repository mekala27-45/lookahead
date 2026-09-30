"""Stage: merge every stage's manifest into results/manifest.json.

Stages write their own manifests under results/manifests so a rerun of one stage never
touches another's figures. This stage merges them in a fixed order, adds the policy
constants, the palette validator's summary, the separate client verification of the live
API and the live browser check as recorded values, and writes the one file every document
renders from.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lookahead_core.config import POLICY, QUANTILE_LEVELS, REGIONS
from lookahead_core.manifest import Manifest, Scribe
from lookahead_core.paths import Paths

ORDER = (
    "data",
    "weather",
    "simulate",
    "recovery",
    "backtest_own",
    "backtest_gbm",
    "skill",
    "hierarchy",
    "events",
    "meter",
    "registry",
    "latency",
)
"""The stage order the pipeline runs in. The Makefile's pipeline target and
scripts/reset_and_rederive.py follow this tuple, and a test holds them to it."""


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    merged = Manifest(as_of=as_of, seed=seed)
    folder = paths.results / "manifests"
    present: list[str] = []
    for name in ORDER:
        path = folder / f"{name}.json"
        if path.exists():
            merged.merge(Manifest.load(path))
            present.append(name)
    _policy(merged)
    _palette(merged, paths.root)
    _deploy(merged, paths.results / "deploy" / "verification.json")
    _live_check(merged, paths.results / "live_check.json")
    merged.put(
        "build.stages_present",
        ", ".join(present) if present else "none",
        "text",
        source="static",
        population="stage manifests found",
        origin="lookahead_registry.stages.assemble",
    )
    merged.save(paths.manifest)
    return merged


def _policy(manifest: Manifest) -> None:
    w = Scribe(
        manifest,
        source="static",
        population="the forecasting protocol",
        origin="lookahead_core.config.POLICY",
    )
    fmts = {
        "issue_hour_utc": "int",
        "horizons": "int",
        "test_months": "int",
        "validation_months": "int",
        "seasonal_naive_lag_hours": "int",
        "gbm_refit_months": "int",
        "gbm_training_window_days": "int",
        "conformal_horizon_bucket_hours": "int",
        "bootstrap_replicates": "int",
        "bootstrap_block_days": "int",
        "interval_level": "pct0",
        "bh_q": "float2",
        "spike_multiple_of_rolling_median": "float1",
        "rolling_median_days": "int",
        "alert_persistence_hours": "int",
        "false_alarm_cost": "float1",
        "missed_event_cost": "float1",
        "recovery_seeds": "int",
        "meter_test_days": "int",
        "meter_profile_window_days": "int",
        "peak_reduction_value_gbp_per_kw": "float1",
        "max_share_significantly_worse_than_operator": "pct0",
        "max_median_peak_timing_error_hours": "float1",
        "max_p99_latency_ms": "ms",
    }
    for field, fmt in fmts.items():
        w.put(f"policy.{field}", getattr(POLICY, field), fmt)
    w.put("policy.quantile_levels", ", ".join(f"{q:.2f}" for q in QUANTILE_LEVELS), "text")
    w.put("policy.quantile_count", len(QUANTILE_LEVELS), "int")
    w.put("policy.ridge_penalties", ", ".join(f"{p:g}" for p in POLICY.ridge_penalties), "text")
    w.put("policy.heating_thresholds", ", ".join(f"{t:g}" for t in POLICY.heating_thresholds_c), "text")
    w.put("policy.cooling_thresholds", ", ".join(f"{t:g}" for t in POLICY.cooling_thresholds_c), "text")
    w.put("policy.alert_threshold_grid", ", ".join(f"{t:g}" for t in POLICY.alert_threshold_grid), "text")
    w.put("policy.coverage_band_90_low", POLICY.coverage_band_90[0], "pct0")
    w.put("policy.coverage_band_90_high", POLICY.coverage_band_90[1], "pct0")
    w.put("policy.meter_cluster_range", ", ".join(str(k) for k in POLICY.meter_cluster_range), "text")
    w.put("policy.region_count", len(REGIONS), "int")


def _palette(manifest: Manifest, root: Path) -> None:
    script = root / "scripts" / "validate_palette.js"
    config = root / "web" / "src" / "theme" / "palette.json"
    w = Scribe(
        manifest,
        source="static",
        population="web/src/theme/palette.json",
        origin="scripts/validate_palette.js",
    )
    if not script.exists() or not config.exists():
        w.put("palette.validated", "not run", "text")
        return
    proc = subprocess.run(
        ["node", str(script), "--config", str(config)], capture_output=True, text=True, check=False
    )
    try:
        summary = json.loads(proc.stdout)
    except json.JSONDecodeError:
        w.put("palette.validated", "validator did not return a summary", "text")
        return
    w.put("palette.failures", int(summary["failures"]), "int")
    w.put("palette.validated", "green" if summary["failures"] == 0 else "failing", "text")
    for mode in ("light", "dark"):
        m = summary["modes"][mode]
        w.put(f"palette.{mode}.worst_adjacent_cvd", m["worstAdjacentCvd"], "float1")
        w.put(f"palette.{mode}.worst_adjacent_normal", m["worstAdjacentNormal"], "float1")
        w.put(f"palette.{mode}.worst_slot_contrast", m["worstSlotContrast"], "float2")
        w.put(f"palette.{mode}.worst_card_contrast", m["worstCardContrast"], "float2")
        w.put(f"palette.{mode}.first_three_all_pairs_cvd", m["firstThreeAllPairsCvd"], "float1")


def _deploy(manifest: Manifest, path: Path) -> None:
    """The separate client verification of the live API, recorded as it was seen."""
    w = Scribe(
        manifest,
        source="recorded",
        population="the live API, checked from a separate client",
        origin="deploy/verify.ps1",
    )
    if not path.exists():
        w.put("deploy.status", "API not deployed", "text")
        return
    seen = json.loads(path.read_text(encoding="utf-8-sig"))
    w.put("deploy.status", "deployed" if seen.get("passed") else "verification failed", "text")
    for key in (
        "base_url",
        "client",
        "checked_at",
        "forecast_id",
        "authority",
        "origin",
        "model_version",
        "backend",
    ):
        w.put(f"deploy.{key}", str(seen.get(key, "")), "text")
    w.put("deploy.health_status", str(seen["health"]["status"]), "text")
    w.put("deploy.health_database", str(seen["health"]["database"]), "text")
    w.put("deploy.forecast_rows_read_back", int(seen["forecast_rows_read_back"]), "int")
    w.put("deploy.median_first_hour_mw", float(seen["median_first_hour_mw"]), "mw")
    w.put("deploy.scored_now", int(seen.get("scored_now", 0)), "int")
    w.put("deploy.unscored_share", float(seen.get("unscored_share", 1.0)), "pct1")
    w.put("deploy.audit_entries", int(seen["audit_entries"]), "int")
    w.put("deploy.audit_before_response", "yes" if seen["audit_before_response"] else "no", "text")
    w.put("deploy.statement_present", "yes" if seen["statement_present"] else "no", "text")
    w.put("deploy.passed", "yes" if seen["passed"] else "no", "text")


def _live_check(manifest: Manifest, path: Path) -> None:
    """The live site and API opened in a real browser after the deploy, as recorded."""
    w = Scribe(
        manifest,
        source="recorded",
        population="the live site and API in a real browser",
        origin="scripts/live_check.py",
    )
    # Before the check has run the keys still exist, so every document renders and says so.
    seen = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not path.exists():
        w.put("live.status", "not checked", "text")
    else:
        w.put("live.status", "passed" if seen.get("passed") else "failed", "text")
    w.put("live.checked_at", str(seen.get("checked_at", "")) or "not yet", "text")
    w.put("live.browser", str(seen.get("browser", "")) or "no browser yet", "text")
    w.put("live.site_url", str(seen.get("site_url", "")), "text")
    w.put("live.routes_loaded", int(seen.get("routes_loaded", 0)), "int")
    w.put("live.routes_total", int(seen.get("routes_total", 0)), "int")
    w.put("live.forecast_id", str(seen.get("forecast_id", "")) or "none", "text")
    w.put(
        "live.asleep_recorded_session_shown",
        "yes" if seen.get("asleep_recorded_session_shown") else "no",
        "text",
    )
    w.put("live.first_probe_status", str(seen.get("first_probe_status", "")), "text")
