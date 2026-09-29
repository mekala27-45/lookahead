"""Stage: the recovery study over conditions and seeds, published as small multiples.

Writes results/recovery/runs.parquet (one row per run and figure), per_authority.parquet
and summary.parquet, and results/manifests/recovery.json with the per condition means,
seed intervals and the callouts' figures.
"""

from __future__ import annotations

import time

import polars as pl
from lookahead_core.config import POLICY
from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths
from lookahead_evaluation.recovery import CONDITIONS, run_study, summarise

CONDITION_LABELS = {
    "base": "base (sensitivity 1.0, noise 1 pct, no missing)",
    "temperature_low": "temperature sensitivity 0.5",
    "temperature_high": "temperature sensitivity 2.0",
    "noise_high": "noise 3 pct",
    "missing_low": "missing 1 pct",
    "missing_high": "missing 5 pct",
}

FIGURES = (
    ("harness.skill_bias", "spct1", "Harness skill bias"),
    ("harness.interval_covers_known", "pct0", "Interval covers the known skill"),
    ("harness.operator_mape_measured", "pct2", "Operator MAPE measured"),
    ("own.mape", "pct2", "own MAPE"),
    ("own.coverage_50", "pct1", "own 50 pct coverage"),
    ("own.coverage_90", "pct1", "own 90 pct coverage"),
    ("own.thresholds_within_2c", "pct0", "Thresholds within 2 C"),
    ("own.holiday_effect_abs_error", "pct2", "Holiday effect error"),
)


def run(
    paths: Paths,
    as_of: str,
    seed: int,
    *,
    seeds: int | None = None,
    conditions: list[str] | None = None,
    workers: int = 2,
) -> Manifest:
    seeds = seeds or POLICY.recovery_seeds
    chosen = conditions or list(CONDITIONS)
    started = time.time()
    records = run_study(chosen, seeds, workers=workers)
    seconds = time.time() - started
    folder = paths.results / "recovery"
    folder.mkdir(parents=True, exist_ok=True)
    runs = pl.DataFrame(
        [
            {"condition": r.condition, "seed": r.seed, "figure": k, "value": v}
            for r in records
            for k, v in r.figures.items()
        ]
    ).sort(["condition", "seed", "figure"])
    per_authority = pl.DataFrame(
        [{"condition": r.condition, "seed": r.seed, **row} for r in records for row in r.per_authority],
        infer_schema_length=None,
    )
    summary = summarise(records)
    runs.write_parquet(folder / "runs.parquet")
    per_authority.write_parquet(folder / "per_authority.parquet")
    summary.write_parquet(folder / "summary.parquet")

    manifest = Manifest(as_of=as_of, seed=seed)
    w = Scribe(
        manifest,
        source="simulated",
        model="own",
        population="the recovery study",
        origin="lookahead_registry.stages.recovery",
        seeds=seeds,
    )
    w.put("recovery.conditions", len(chosen), "int")
    w.put("recovery.seeds_per_condition", seeds, "int")
    w.put("recovery.runs", len(records), "int")
    w.put("recovery.seconds", seconds, "float1")
    w.put("recovery.known_skill", float(records[0].figures["harness.known_skill"]), "pct1")
    figure_names = [k for k, _, _ in FIGURES]
    extra = sorted(
        {k for r in records for k in r.figures}
        - set(figure_names)
        - {
            "harness.known_skill",
            "harness.operator_mape_known",
            "harness.origins",
            "own.fits",
            "harness.skill_abs_bias",
        }
    )
    for condition in chosen:
        sub = summary.filter(pl.col("condition") == condition)
        for key, fmt, _ in FIGURES:
            row = sub.filter(pl.col("figure") == key)
            if row.height == 0:
                continue
            w.put(f"recovery.{condition}.{key}", float(row["mean"][0]), fmt, condition=condition)
            w.put(f"recovery.{condition}.{key}_lower", float(row["lower"][0]), fmt, condition=condition)
            w.put(f"recovery.{condition}.{key}_upper", float(row["upper"][0]), fmt, condition=condition)
        for key in extra:
            row = sub.filter(pl.col("figure") == key)
            if row.height == 0:
                continue
            fmt = (
                "pct1"
                if ("coverage" in key or "recall" in key or "precision" in key or "share" in key)
                else "float3"
            )
            w.put(f"recovery.{condition}.{key}", float(row["mean"][0]), fmt, condition=condition)
            w.put(f"recovery.{condition}.{key}_lower", float(row["lower"][0]), fmt, condition=condition)
            w.put(f"recovery.{condition}.{key}_upper", float(row["upper"][0]), fmt, condition=condition)
    rows: list[list[Scalar]] = []
    for condition in chosen:
        sub = summary.filter(pl.col("condition") == condition)
        cells: list[Scalar] = [CONDITION_LABELS.get(condition, condition)]
        for key, _, _ in FIGURES:
            row = sub.filter(pl.col("figure") == key)
            cells.append(float(row["mean"][0]) if row.height else None)
        rows.append(cells)
    w.table(
        "recovery.by_condition",
        ["Condition", *[label for _, _, label in FIGURES]],
        ["text", *[fmt for _, fmt, _ in FIGURES]],
        rows,
    )
    worst = summary.filter(pl.col("figure") == "harness.interval_covers_known").sort("mean").head(1)
    w.put(
        "recovery.worst_condition_for_harness",
        CONDITION_LABELS.get(str(worst["condition"][0]), str(worst["condition"][0]))
        if worst.height
        else "none",
        "text",
    )
    worst_cov = (
        summary.filter(pl.col("figure") == "own.coverage_90")
        .with_columns((pl.col("mean") - 0.9).abs().alias("gap"))
        .sort("gap", descending=True)
        .head(1)
    )
    w.put(
        "recovery.worst_condition_for_coverage",
        CONDITION_LABELS.get(str(worst_cov["condition"][0]), str(worst_cov["condition"][0]))
        if worst_cov.height
        else "none",
        "text",
    )
    manifest.save(paths.results / "manifests" / "recovery.json")
    return manifest
