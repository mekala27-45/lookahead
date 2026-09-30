"""The recovery study: the harness, the backend, the reconciliation and the detector graded on
a grid with known truth, over conditions and seeds.

Each run simulates a grid under one condition and seed, quarantines it the way the real feed
is quarantined, and measures what the build measures on real data, where the answer is known:
the harness's skill score for an oracle forecaster with a known error against the synthetic
operator (known skill, so the bias and the interval coverage of the harness are measurable);
the own backend's coverage against nominal and its recovered thresholds and holiday effect
against the planted ones; the reconciliation methods' coherence and their accuracy against the
truth; the detector's precision and recall on the planted events. Conditions vary the
temperature sensitivity, the noise level and the missing data rate one at a time from a base.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from lookahead_contracts import quarantine
from lookahead_core.config import POLICY
from lookahead_forecast.interface import ForecastSpec, PanelData
from lookahead_forecast.own import OwnForecaster
from lookahead_sim import GridSpec, events_frame, raw_observations, simulate
from lookahead_sim.oracle import OracleForecaster

from lookahead_evaluation.bootstrap import bootstrap_statistic
from lookahead_evaluation.harness import run_backend
from lookahead_evaluation.metrics import (
    day_sums,
    row_errors,
    stat_coverage_50,
    stat_coverage_90,
    stat_mape,
    stat_mape_operator,
    stat_skill,
    sums_matrix,
)

CONDITIONS: dict[str, GridSpec] = {
    "base": GridSpec(),
    "temperature_low": GridSpec(temperature_sensitivity=0.5),
    "temperature_high": GridSpec(temperature_sensitivity=2.0),
    "noise_high": GridSpec(noise_sigma=0.03),
    "missing_low": GridSpec(missing_rate=0.01),
    "missing_high": GridSpec(missing_rate=0.05),
}

SIM_WINDOWS: dict[str, str | int] = {
    "training_start": "2023-01-01",
    "validation_start": "2024-01-01",
    "test_start": "2025-01-01",
    "test_end": "2025-12-30",
}

ORACLE_SIGMA = 0.015

Extension = Callable[
    [PanelData, pl.DataFrame, pl.DataFrame, pl.DataFrame, dict[str, Any], int], dict[str, float]
]
"""Later steps register the reconciliation and the detector here: (data, panel, subregions, hierarchy, truth, seed) -> figures."""

EXTENSIONS: dict[str, Extension] = {}


@dataclass
class RunRecord:
    condition: str
    seed: int
    figures: dict[str, float] = field(default_factory=dict)
    per_authority: list[dict[str, Any]] = field(default_factory=list)


def _known_skill(spec: GridSpec) -> float:
    from lookahead_sim.grid import _expected_operator_mape
    from lookahead_sim.oracle import expected_mape

    return 1.0 - expected_mape(ORACLE_SIGMA) / _expected_operator_mape(spec)


def run_one(condition: str, seed: int) -> RunRecord:
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    spec = CONDITIONS[condition]
    grid = simulate(spec, seed)
    quarantined = quarantine.apply_rules(raw_observations(grid))
    panel = quarantined.panel
    data = PanelData.from_frames(panel, None, SIM_WINDOWS, "simulated")
    record = RunRecord(condition=condition, seed=seed)
    figures = record.figures

    # 1. The harness on the oracle: measured skill against the known skill, per authority.
    oracle = OracleForecaster(sigma=ORACLE_SIGMA, seed=seed)
    result = run_backend(data, oracle, ForecastSpec(backend="oracle"))
    errors = row_errors(result.scoring).filter(pl.col("has_operator") == 1.0)
    known = _known_skill(spec)
    covered = 0
    biases: list[float] = []
    op_mapes: list[float] = []
    for authority in data.names:
        sums = sums_matrix(day_sums(errors.filter(pl.col("authority") == authority)))
        skill, lower, upper, _ = bootstrap_statistic(sums, stat_skill, seed, "recovery", authority)
        covered += int(lower <= known <= upper)
        biases.append(skill - known)
        op_mapes.append(float(stat_mape_operator(sums.sum(axis=0, keepdims=True))[0]))
        record.per_authority.append(
            {
                "authority": authority,
                "component": "harness",
                "measured_skill": skill,
                "known_skill": known,
                "lower": lower,
                "upper": upper,
            }
        )
    figures["harness.known_skill"] = known
    figures["harness.skill_bias"] = float(np.mean(biases))
    figures["harness.skill_abs_bias"] = float(np.mean(np.abs(biases)))
    figures["harness.interval_covers_known"] = covered / len(data.names)
    figures["harness.operator_mape_measured"] = float(np.mean(op_mapes))
    figures["harness.operator_mape_known"] = grid.truth[data.names[0]]["operator_mape_expected"]
    figures["harness.origins"] = float(result.predictions.origins)

    # 2. The own backend: coverage against nominal, thresholds and holiday effect against the truth.
    own = OwnForecaster()
    own_result = run_backend(data, own, ForecastSpec(backend="own"))
    own_errors = row_errors(own_result.scoring)
    sums = sums_matrix(day_sums(own_errors))
    totals = sums.sum(axis=0, keepdims=True)
    figures["own.mape"] = float(stat_mape(totals)[0])
    figures["own.coverage_50"] = float(stat_coverage_50(totals)[0])
    figures["own.coverage_90"] = float(stat_coverage_90(totals)[0])
    figures["own.fits"] = float(own_result.predictions.fits)
    fitted = own_result.fitted  # the fit the backtest already made; a second search doubled the run
    heat_err: list[float] = []
    cool_err: list[float] = []
    holiday_err: list[float] = []
    for authority in data.names:
        chosen = fitted.chosen[authority]
        truth = grid.truth[authority]
        heat_err.append(abs(chosen["heating_threshold_c"] - truth["heating_threshold_c"]))
        cool_err.append(abs(chosen["cooling_threshold_c"] - truth["cooling_threshold_c"]))
        state = fitted.states[authority]
        beta = state.solve()
        idx = state.names.index("holiday")
        # The coefficient is on a standardized column; undo the scaling to read it as a ratio effect.
        holiday_effect = float(beta[idx] / state.std[idx])
        holiday_err.append(abs(holiday_effect - truth["holiday_effect"]))
        record.per_authority.append(
            {
                "authority": authority,
                "component": "own",
                "heating_chosen": chosen["heating_threshold_c"],
                "heating_true": truth["heating_threshold_c"],
                "cooling_chosen": chosen["cooling_threshold_c"],
                "cooling_true": truth["cooling_threshold_c"],
                "holiday_fitted": holiday_effect,
                "holiday_true": truth["holiday_effect"],
            }
        )
    figures["own.heating_threshold_abs_error_c"] = float(np.mean(heat_err))
    figures["own.cooling_threshold_abs_error_c"] = float(np.mean(cool_err))
    figures["own.thresholds_within_2c"] = float(
        np.mean([(h <= 2.0) and (c <= 2.0) for h, c in zip(heat_err, cool_err, strict=True)])
    )
    figures["own.holiday_effect_abs_error"] = float(np.mean(holiday_err))

    # 3. Later components, registered by the hierarchy and events packages.
    for name, extension in EXTENSIONS.items():
        figures.update(
            {
                f"{name}.{k}": v
                for k, v in extension(
                    data,
                    panel,
                    grid.subregions,
                    grid.hierarchy,
                    {
                        "truth": grid.truth,
                        "events": events_frame(grid),
                        "own_scoring": own_result.scoring,
                        "own_fitted": fitted,
                    },
                    seed,
                ).items()
            }
        )
    return record


CHECKPOINT_ENV = "LOOKAHEAD_RECOVERY_CHECKPOINTS"
"""A directory; when set, every finished (condition, seed) record is written there as JSON and a
rerun reads it back instead of running the condition again. The build machine restarts without
notice; a record read back is the record that was computed. The rederive never sets it."""


def _checkpoint_path(condition: str, seed: int) -> Path | None:
    folder = os.environ.get(CHECKPOINT_ENV, "").strip()
    return Path(folder) / f"{condition}-{seed}.json" if folder else None


def _worker(args: tuple[str, int]) -> RunRecord:
    condition, seed = args
    path = _checkpoint_path(condition, seed)
    if path is not None and path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        return RunRecord(**raw)
    record = run_one(condition, seed)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(record)), encoding="utf-8")
    return record


def run_study(conditions: list[str], seeds: int, workers: int = 2) -> list[RunRecord]:
    jobs = [(c, s) for c in conditions for s in range(seeds)]
    if workers <= 1:
        return [_worker(job) for job in jobs]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_worker, jobs))


def summarise(records: list[RunRecord]) -> pl.DataFrame:
    """Per condition and figure: the mean over seeds, the seed interval, and the seed count."""
    rows = []
    for r in records:
        for k, v in r.figures.items():
            rows.append({"condition": r.condition, "seed": r.seed, "figure": k, "value": v})
    frame = pl.DataFrame(rows)
    alpha = (1 - POLICY.interval_level) / 2
    return (
        frame.group_by(["condition", "figure"])
        .agg(
            pl.col("value").mean().alias("mean"),
            pl.col("value").quantile(alpha).alias("lower"),
            pl.col("value").quantile(1 - alpha).alias("upper"),
            pl.col("value").std().alias("sd"),
            pl.len().alias("seeds"),
        )
        .sort(["condition", "figure"])
    )
