"""Stage: anomaly detection on the real grid, graded on the known events table.

Three parts. The operating point: the alert threshold chosen on the demonstration grid's
validation year, where the simulator planted one event of each kind per authority, by the
stated cost of a false alarm and a missed event, with the interior test, then reported on
the grid's test year. The test year: the own backend's short horizon residuals from the
backtest, standardized by the residual scale its conformal calibration measured on the
validation year, run through the persistence rule and classified, with every alert and every
standardized residual written for the page. The known events: for every row of
data/known_events.csv the own backend is fit on the year before a window around the event
and run over the window, so the residuals there are those of a model that has seen nothing
after each origin, and the detector's recall, detection hour and false alarm rate on the rest
of each window are published. Writes results/events/*.parquet, operating_point.json and
results/manifests/events.json.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import polars as pl
from lookahead_core.config import POLICY
from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths
from lookahead_evaluation.harness import run_backend
from lookahead_events.detect import FLAG_COLUMNS, ResidualScale, alerts_frame, find_alerts, standardize
from lookahead_events.grade import grade
from lookahead_events.operating import OperatingPoint, choose_threshold
from lookahead_events.recovery_extension import attach_raw, test_frame, validation_frame
from lookahead_forecast.interface import ForecastSpec, PanelData
from lookahead_forecast.own import OwnForecaster

from lookahead_registry.stages.data import load_panel

WINDOW_DAYS = 10
"""Days on either side of a known event that its window covers."""


def _sim_operating_point(paths: Paths) -> tuple[OperatingPoint, dict[str, Any]]:
    panel = pl.read_parquet(paths.sim / "panel.parquet")
    windows = json.loads((paths.sim / "windows.json").read_text(encoding="utf-8"))
    events = pl.read_csv(paths.sim / "events.csv", try_parse_dates=True).with_columns(
        pl.col("start_utc").dt.replace_time_zone("UTC")
    )
    if "window" not in events.columns:
        raise ValueError("data/sim/events.csv has no window column; run `lookahead simulate` again")
    data = PanelData.from_frames(panel, None, windows, "simulated")
    spec = ForecastSpec(backend="own")
    result = run_backend(data, OwnForecaster(), spec)
    frame_val, scales = validation_frame(result.fitted, data)
    standardized_val = standardize(attach_raw(frame_val, panel), scales)
    point = choose_threshold(standardized_val, events.filter(pl.col("window") == "validation"))
    standardized_test = standardize(attach_raw(test_frame(result.scoring), panel), scales)
    alerts = find_alerts(standardized_test, point.threshold, POLICY.alert_persistence_hours)
    g = grade(alerts, events.filter(pl.col("window") == "test"))
    sim = {
        "load_sheds": g.load_sheds,
        "load_sheds_detected": g.load_sheds_detected,
        "defects": g.defects,
        "defects_recovered": g.defects_recovered,
        "defects_called_events": g.defects_called_events,
        "demand_alerts": g.demand_alerts,
        "defect_alerts": g.defect_alerts,
        "false_alarms": g.false_alarms,
        "mean_delay_hours": g.mean_delay_hours,
        "detections": g.detections,
    }
    return point, sim


def _export_scales(paths: Paths) -> dict[str, ResidualScale]:
    export = paths.results / "models" / "own_model.json"
    if not export.exists():
        raise FileNotFoundError(
            "results/models/own_model.json is missing; run `lookahead backtest --backend own`"
        )
    payload = json.loads(export.read_text(encoding="utf-8"))
    scales = {}
    for authority, a in payload["authorities"].items():
        if float(a.get("residual_scale", 0.0)) > 0:
            scales[authority] = ResidualScale(
                center=float(a["residual_center"]),
                scale=float(a["residual_scale"]),
                rows=int(a["residual_rows"]),
            )
    return scales


def _known_event_window(
    row: dict[str, Any], panel: pl.DataFrame, subregions: pl.DataFrame, weather: pl.DataFrame
) -> tuple[PanelData, pl.DataFrame]:
    """The series of the event's node with windows around the event; returns the data and the raw
    frame (demand_raw with the flags) the detector standardizes against."""
    node = str(row["node"])
    authority = str(row["authority"])
    onset: datetime = row["onset_utc"]
    end: datetime = row["end_utc"]
    test_start = (onset - timedelta(days=WINDOW_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    test_end = (end + timedelta(days=WINDOW_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
    validation_start = test_start - timedelta(days=365)
    base = panel.filter(
        (pl.col("authority") == authority) & (pl.col("utc_hour") < test_end + timedelta(days=3))
    )
    if "." in node:
        sub = node.split(".", 1)[1]
        series = (
            subregions.filter((pl.col("authority") == authority) & (pl.col("subregion") == sub))
            .select("utc_hour", pl.col("demand").cast(pl.Float64).alias("demand_raw"))
            .join(base.select("utc_hour", "utc_offset_hours", "region"), on="utc_hour", how="inner")
            .with_columns(
                pl.lit(node).alias("authority"),
                pl.lit(None, dtype=pl.Float64).alias("forecast_operator"),
                pl.col("demand_raw").is_null().alias("demand_missing"),
                (pl.col("demand_raw") <= 0).fill_null(False).alias("demand_nonpositive"),
                pl.lit(False).alias("demand_spike"),
                pl.lit(False).alias("duplicate_hour"),
                pl.lit(False).alias("missing_hour"),
            )
            .with_columns(
                pl.when(pl.col("demand_missing") | pl.col("demand_nonpositive"))
                .then(None)
                .otherwise(pl.col("demand_raw"))
                .alias("demand")
            )
            .sort("utc_hour")
        )
        node_weather = weather.filter(pl.col("authority") == authority).with_columns(
            pl.lit(node).alias("authority")
        )
    else:
        series = base.with_columns(pl.col("demand_raw").cast(pl.Float64))
        node_weather = weather.filter(pl.col("authority") == authority)
    series = series.filter(pl.col("utc_hour") < test_end + timedelta(days=3))
    windows: dict[str, str | int] = {
        "training_start": "2018-07-01",
        "validation_start": validation_start.date().isoformat(),
        "test_start": test_start.date().isoformat(),
        "test_end": test_end.date().isoformat(),
    }
    data = PanelData.from_frames(series, node_weather, windows, "real:eia930")
    raw = series.select(
        "authority", "utc_hour", "demand_raw", *[c for c in FLAG_COLUMNS if c in series.columns]
    )
    return data, raw


def run(paths: Paths, as_of: str, seed: int, *, known: bool = True) -> Manifest:
    started = time.time()
    folder = paths.results / "events"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(as_of=as_of, seed=seed)

    # 1. The operating point, chosen on the demonstration grid's validation year.
    point, sim = _sim_operating_point(paths)
    (folder / "operating_point.json").write_text(
        json.dumps(
            {
                "threshold": point.threshold,
                "persistence_hours": point.persistence_hours,
                "false_alarm_cost": point.false_alarm_cost,
                "missed_event_cost": point.missed_event_cost,
                "cost": point.cost,
                "interior": point.interior,
                "grid": list(point.grid),
                "costs": {str(k): v for k, v in point.costs.items()},
                "false_alarms": {str(k): v for k, v in point.false_alarms.items()},
                "missed": {str(k): v for k, v in point.missed.items()},
                "chosen_on": "the demonstration grid's validation year (seed of data/sim), planted events",
                "reported_on": "the demonstration grid's test year and the real grid",
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    w = Scribe(
        manifest,
        source="simulated",
        model="own",
        population="the demonstration grid, validation year for the choice and test year for the grade",
        origin="lookahead_registry.stages.events",
    )
    w.put("events.threshold", point.threshold, "float1")
    w.put("events.persistence_hours", point.persistence_hours, "int")
    w.put("events.false_alarm_cost", point.false_alarm_cost, "float1")
    w.put("events.missed_event_cost", point.missed_event_cost, "float1")
    w.put("events.validation_cost", point.cost, "float1")
    w.put("events.interior", "yes" if point.interior else "no", "text")
    w.put("events.grid_low", min(point.grid), "float1")
    w.put("events.grid_high", max(point.grid), "float1")
    w.table(
        "events.operating_grid",
        ["Threshold", "False alarms", "Missed load sheds", "Cost"],
        ["float1", "int", "int", "float1"],
        [[t, point.false_alarms[t], point.missed[t], point.costs[t]] for t in point.grid],
    )
    w.put("events.sim.load_sheds", sim["load_sheds"], "int")
    w.put("events.sim.load_sheds_detected", sim["load_sheds_detected"], "int")
    w.put(
        "events.sim.recall_load_shed",
        sim["load_sheds_detected"] / sim["load_sheds"] if sim["load_sheds"] else 0.0,
        "pct0",
    )
    w.put("events.sim.defects", sim["defects"], "int")
    w.put("events.sim.defects_recovered", sim["defects_recovered"], "int")
    w.put("events.sim.defects_called_events", sim["defects_called_events"], "int")
    w.put("events.sim.false_alarms", sim["false_alarms"], "int")
    w.put("events.sim.demand_alerts", sim["demand_alerts"], "int")
    w.put(
        "events.sim.precision",
        (sim["demand_alerts"] - sim["false_alarms"]) / sim["demand_alerts"] if sim["demand_alerts"] else 1.0,
        "pct0",
    )
    w.put(
        "events.sim.mean_delay_hours",
        float(sim["mean_delay_hours"]) if sim["mean_delay_hours"] == sim["mean_delay_hours"] else 0.0,
        "float1",
    )

    # 2. The real test year.
    panel = load_panel(paths)
    scoring_path = paths.results / "backtest" / "own" / "scoring.parquet"
    if not scoring_path.exists():
        raise FileNotFoundError("results/backtest/own/scoring.parquet is missing; run the own backtest first")
    scoring = pl.read_parquet(scoring_path)
    scales = _export_scales(paths)
    standardized = standardize(attach_raw(test_frame(scoring), panel), scales).filter(
        pl.col("residual_scale").is_not_null()
    )
    alerts = find_alerts(standardized, point.threshold, point.persistence_hours)
    frame = alerts_frame(alerts).sort(["start", "authority"])
    frame.write_parquet(folder / "alerts.parquet")
    standardized.select(
        "authority", "utc_hour", "pred", "demand_raw", "residual", "z", "flagged"
    ).write_parquet(folder / "residuals.parquet", compression="zstd")
    hours = standardized.height
    w = Scribe(
        manifest,
        source="real:eia930",
        model="own",
        population=f"{standardized['authority'].n_unique()} authorities in the backtest, test year",
        origin="lookahead_registry.stages.events",
    )
    demand_alerts = [a for a in alerts if a.kind == "demand_event"]
    defect_alerts = [a for a in alerts if a.kind == "data_defect"]
    w.put("events.test.hours", hours, "int")
    w.put("events.test.authorities", standardized["authority"].n_unique(), "int")
    w.put("events.test.alerts", len(alerts), "int")
    w.put("events.test.demand_events", len(demand_alerts), "int")
    w.put("events.test.data_defects", len(defect_alerts), "int")
    w.put("events.test.alerts_per_1000_hours", 1000.0 * len(alerts) / hours if hours else 0.0, "float2")
    w.put(
        "events.test.demand_events_per_1000_hours",
        1000.0 * len(demand_alerts) / hours if hours else 0.0,
        "float2",
    )
    w.put(
        "events.test.demand_event_hours_share",
        sum(a.hours for a in demand_alerts) / hours if hours else 0.0,
        "pct2",
    )
    w.put(
        "events.test.low_share",
        (sum(1 for a in demand_alerts if a.direction == "low") / len(demand_alerts))
        if demand_alerts
        else 0.0,
        "pct0",
    )
    by_authority = (
        frame.group_by("authority")
        .agg(
            pl.len().alias("alerts"),
            (pl.col("kind") == "demand_event").sum().alias("demand_events"),
            (pl.col("kind") == "data_defect").sum().alias("data_defects"),
            pl.col("hours").sum().alias("hours"),
            pl.col("peak_z").max().alias("peak_z"),
        )
        # The authority breaks ties, so the table's row order is the same on every run.
        .sort(["alerts", "authority"], descending=[True, False])
    )
    by_authority.write_parquet(folder / "by_authority.parquet")
    w.table(
        "events.test.by_authority",
        ["Authority", "Alerts", "Demand events", "Data defects", "Alert hours", "Peak z"],
        ["text", "int", "int", "int", "int", "float1"],
        [list(r) for r in by_authority.iter_rows()],
    )
    top = frame.filter(pl.col("kind") == "demand_event").sort("peak_z", descending=True).head(25)
    w.table(
        "events.test.largest",
        ["Authority", "Start (UTC)", "Hours", "Direction", "Peak z", "Mean z", "Flags"],
        ["text", "text", "int", "text", "float1", "float1", "text"],
        [
            [
                r["authority"],
                r["start"].strftime("%Y-%m-%d %H:%M"),
                r["hours"],
                r["direction"],
                r["peak_z"],
                r["mean_z"],
                r["flags"],
            ]
            for r in top.iter_rows(named=True)
        ],
    )
    w.put("events.test.residual_scale_median", float(np.median([s.scale for s in scales.values()])), "pct2")

    # 3. The known events.
    if known:
        _known_events(paths, panel, point, manifest, folder)
    w.put("events.seconds", time.time() - started, "float1")
    manifest.save(paths.results / "manifests" / "events.json")
    return manifest


def _known_events(
    paths: Paths, panel: pl.DataFrame, point: OperatingPoint, manifest: Manifest, folder: Any
) -> None:
    table = pl.read_csv(paths.data / "known_events.csv", try_parse_dates=True).with_columns(
        pl.col("onset_utc").dt.replace_time_zone("UTC"), pl.col("end_utc").dt.replace_time_zone("UTC")
    )
    subregions = pl.read_parquet(paths.eia / "subregions.parquet")
    weather = pl.read_parquet(paths.weather / "hourly.parquet")
    first_hour = panel["utc_hour"].min()
    last_hour = panel["utc_hour"].max()
    assert isinstance(first_hour, datetime) and isinstance(last_hour, datetime)
    rows: list[list[Scalar]] = []
    graded: list[dict[str, Any]] = []
    windows_frames: list[pl.DataFrame] = []
    detected = 0
    false_alarms = 0
    outside_hours = 0
    delays: list[float] = []
    spec = ForecastSpec(backend="own")
    for row in table.iter_rows(named=True):
        if not (first_hour <= row["onset_utc"] <= last_hour):
            raise ValueError(f"known event {row['event']} at {row['onset_utc']} is outside the data window")
        data, raw = _known_event_window(row, panel, subregions, weather)
        result = run_backend(data, OwnForecaster(), spec)
        _, scales = validation_frame(result.fitted, data)
        standardized = standardize(attach_raw(test_frame(result.scoring), raw), scales)
        alerts = find_alerts(standardized, point.threshold, point.persistence_hours)
        events = pl.DataFrame(
            {
                "event": [row["event"]],
                "kind": ["demand_event"],
                "authority": [str(row["node"])],
                "onset_utc": pl.Series([row["onset_utc"]], dtype=pl.Datetime("us", "UTC")),
                "end_utc": pl.Series([row["end_utc"]], dtype=pl.Datetime("us", "UTC")),
            }
        )
        g = grade(alerts, events)
        d = g.detections[0]
        detected += int(d["detected"])
        false_alarms += g.false_alarms
        span_hours = int((row["end_utc"] - row["onset_utc"]) / timedelta(hours=1)) + 1
        outside_hours += max(standardized.height - span_hours, 0)
        if d["detected"]:
            delays.append(float(d["delay_hours"]))
        peak = float(d["peak_z"]) if d["peak_z"] is not None else None
        rows.append(
            [
                str(row["event"]),
                str(row["node"]),
                row["onset_utc"].strftime("%Y-%m-%d %H:%M"),
                "detected" if d["detected"] else "missed",
                d["detection_hour"].strftime("%Y-%m-%d %H:%M") if d["detection_hour"] else "none",
                float(d["delay_hours"]) if d["delay_hours"] is not None else None,
                peak,
                g.false_alarms,
            ]
        )
        graded.append(
            {
                "event": row["event"],
                "node": row["node"],
                "authority": row["authority"],
                "onset_utc": row["onset_utc"],
                "end_utc": row["end_utc"],
                "detected": bool(d["detected"]),
                "detection_hour": d["detection_hour"],
                "delay_hours": d["delay_hours"],
                "peak_z": peak,
                "false_alarms_in_window": g.false_alarms,
                "window_hours": standardized.height,
                "alerts_in_window": len(alerts),
                "citation": row["citation"],
            }
        )
        windows_frames.append(
            standardized.select("authority", "utc_hour", "pred", "demand_raw", "z", "flagged").with_columns(
                pl.lit(str(row["event"])).alias("event")
            )
        )
    pl.DataFrame(graded).write_parquet(folder / "known_events.parquet")
    pl.concat(windows_frames).write_parquet(folder / "known_event_windows.parquet", compression="zstd")
    w = Scribe(
        manifest,
        source="real:eia930",
        model="own",
        population="the known events table, each in a window of ten days either side",
        origin="lookahead_registry.stages.events",
    )
    w.put("events.known.rows", table.height, "int")
    w.put("events.known.events", table["event"].n_unique(), "int")
    w.put("events.known.detected", detected, "int")
    w.put("events.known.recall", detected / table.height if table.height else 0.0, "pct0")
    w.put("events.known.false_alarms_outside", false_alarms, "int")
    w.put("events.known.hours_outside", outside_hours, "int")
    w.put(
        "events.known.false_alarms_per_1000_hours",
        1000.0 * false_alarms / outside_hours if outside_hours else 0.0,
        "float2",
    )
    w.put("events.known.median_delay_hours", float(np.median(delays)) if delays else 0.0, "float1")
    w.table(
        "events.known.table",
        [
            "Event",
            "Node",
            "Onset (UTC)",
            "Verdict",
            "Detection hour (UTC)",
            "Delay hours",
            "Peak z",
            "False alarms in window",
        ],
        ["text", "text", "text", "text", "text", "float1", "float1", "int"],
        rows,
    )
    missed = [f"{g['event']} at {g['node']}" for g in graded if not g["detected"]]
    w.put("events.known.missed_list", ", ".join(missed) if missed else "none", "text")
