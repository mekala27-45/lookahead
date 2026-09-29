"""Stage: the synthetic grid for the demonstration seed, with its truth tables.

Writes data/sim/panel.parquet (the quarantined observations with the truth columns beside
them), data/sim/subregions.parquet, data/sim/events.csv, data/sim/hierarchy.csv,
data/sim/truth.json and data/sim/spec.json, and results/manifests/simulate.json.
"""

from __future__ import annotations

import json

import polars as pl
from lookahead_contracts import quarantine
from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths
from lookahead_sim import GridSpec, events_frame, raw_observations, simulate

SIM_WINDOWS: dict[str, str | int] = {
    "training_start": "2023-01-01",
    "validation_start": "2024-01-01",
    "test_start": "2025-01-01",
    "test_end": "2025-12-30",
    "test_days": 364,
    "validation_days": 366,
}


def build(
    spec: GridSpec, seed: int
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, dict[str, dict[str, float]], list[dict[str, object]]]:
    grid = simulate(spec, seed)
    quarantined = quarantine.apply_rules(raw_observations(grid))
    panel = quarantined.panel.drop("source_file")
    events = events_frame(grid)
    return panel, grid.subregions, grid.hierarchy, grid.truth, events.to_dicts()


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    spec = GridSpec()
    panel, subregions, hierarchy, truth, events = build(spec, seed)
    paths.sim.mkdir(parents=True, exist_ok=True)
    panel.write_parquet(paths.sim / "panel.parquet", compression="zstd")
    subregions.write_parquet(paths.sim / "subregions.parquet", compression="zstd")
    hierarchy.write_csv(paths.sim / "hierarchy.csv")
    pl.DataFrame(events).write_csv(paths.sim / "events.csv")
    (paths.sim / "truth.json").write_text(
        json.dumps(truth, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    (paths.sim / "spec.json").write_text(
        json.dumps(spec.model_dump(mode="json"), indent=1, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    (paths.sim / "windows.json").write_text(json.dumps(SIM_WINDOWS, indent=1) + "\n", encoding="utf-8")

    manifest = Manifest(as_of=as_of, seed=seed)
    w = Scribe(
        manifest,
        source="simulated",
        population="the demonstration grid",
        origin="lookahead_registry.stages.simulate",
        seed=seed,
    )
    w.put("sim.authorities", panel["authority"].n_unique(), "int")
    w.put("sim.hours", panel.filter(pl.col("authority") == panel["authority"][0]).height, "int")
    w.put("sim.years", spec.years, "int")
    w.put("sim.regions", hierarchy.filter(pl.col("level") == 2).height, "int")
    w.put("sim.subregions", hierarchy.filter(pl.col("level") == 4).height, "int")
    w.put("sim.noise_sigma", spec.noise_sigma, "pct1")
    w.put("sim.noise_phi", spec.noise_phi, "float2")
    w.put("sim.operator_error_sigma", spec.operator_error_sigma, "pct1")
    w.put("sim.operator_bias", spec.operator_bias, "pct1")
    w.put("sim.operator_mape_expected", next(iter(truth.values()))["operator_mape_expected"], "pct2")
    w.put("sim.subregion_gap", spec.subregion_gap, "pct1")
    w.put("sim.planted_events", len(events), "int")
    w.put("sim.quarantined_rows", int(panel["quarantined"].sum()), "int")
    rows: list[list[Scalar]] = [
        [
            str(e["kind"]),
            str(e["authority"]),
            str(e["start_utc"]),
            int(str(e["duration_hours"])),
            float(str(e["size_share"])),
        ]
        for e in events
    ]
    w.table(
        "sim.events",
        ["Kind", "Authority", "Start (UTC)", "Hours", "Size"],
        ["text", "text", "text", "int", "pct1"],
        rows,
    )
    truth_rows: list[list[Scalar]] = [
        [
            name,
            t["base_mw"],
            t["heating_threshold_c"],
            t["cooling_threshold_c"],
            t["heating_slope_mw_per_c"],
            t["cooling_slope_mw_per_c"],
            t["holiday_effect"],
        ]
        for name, t in sorted(truth.items())
    ]
    w.table(
        "sim.truth",
        [
            "Authority",
            "Base (MW)",
            "Heating threshold (C)",
            "Cooling threshold (C)",
            "Heating slope (MW per C)",
            "Cooling slope (MW per C)",
            "Holiday effect",
        ],
        ["text", "mw", "float1", "float1", "float1", "float1", "spct1"],
        truth_rows,
    )
    manifest.save(paths.results / "manifests" / "simulate.json")
    return manifest


def load_sim_panel(paths: Paths) -> pl.DataFrame:
    return pl.read_parquet(paths.sim / "panel.parquet")
