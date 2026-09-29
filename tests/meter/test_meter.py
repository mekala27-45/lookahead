"""The meter: clusters, matching, the high price events, the estimator on a planted response,
the plan hash, and the second hierarchy's arithmetic."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from lookahead_meter.clusters import cluster_households, describe, peak_shares
from lookahead_meter.forecast import TOTAL, cluster_panel, meter_windows, summing_for
from lookahead_meter.plan import PLAN, plan_hash
from lookahead_meter.tou import analyse, high_price_events, match_households, slot_table

ROOT = Path(__file__).resolve().parents[2]
HALF_HOUR = timedelta(minutes=30)


def _profiles(n: int, seed: int = 0) -> pl.DataFrame:
    """Synthetic household profiles from three shapes: evening peak, morning peak, flat."""
    rng = np.random.default_rng(seed)
    slots = np.arange(48)
    shapes = {
        "evening": 1.0 + 0.8 * np.exp(-((slots - 37) ** 2) / 8.0),
        "morning": 1.0 + 0.8 * np.exp(-((slots - 15) ** 2) / 8.0),
        "flat": np.ones(48),
    }
    rows = []
    for i in range(n):
        household = f"H{i:04d}"
        tariff = "ToU" if i % 5 == 0 else "Std"
        shape = list(shapes)[i % 3]
        mean = float(rng.uniform(0.1, 0.5))
        for daytype in ("weekday", "weekend"):
            profile = shapes[shape] * (1.0 + rng.normal(0, 0.03, 48))
            profile = profile / profile.mean()
            for slot in range(48):
                rows.append((household, tariff, daytype, slot, mean * profile[slot], 200, mean, 300))
    return pl.DataFrame(
        rows, schema=["household", "tariff", "daytype", "slot", "kwh", "n", "mean_kwh", "days"], orient="row"
    )


def test_cluster_count_equals_the_chosen_count_and_shapes_are_named() -> None:
    clustering = cluster_households(_profiles(120), seed=3)
    assert clustering.k == clustering.assignment["cluster"].n_unique()
    assert clustering.k == max(clustering.silhouette_by_k, key=lambda k: (clustering.silhouette_by_k[k], -k))
    assert clustering.k == 3, "three planted shapes"
    assert set(clustering.labels.values()) <= {
        "evening peak",
        "morning peak",
        "flat",
        "double peak",
        "night heavy",
    }
    assert sorted(clustering.labels.values()) == ["evening peak", "flat", "morning peak"]
    shares = peak_shares(_profiles(120), clustering.assignment)
    assert abs(shares["evening_peak_share"].sum() - 1.0) < 1e-9
    assert shares.sort("evening_peak_share", descending=True)["cluster"][0] == 0, (
        "cluster 0 carries the evening peak"
    )


def test_clustering_is_deterministic_in_the_seed() -> None:
    a = cluster_households(_profiles(90), seed=5).assignment
    b = cluster_households(_profiles(90), seed=5).assignment
    assert a.equals(b)


def test_describe_names_the_shapes() -> None:
    slots = np.arange(48)
    evening = np.concatenate([1.0 + 0.8 * np.exp(-((slots - 37) ** 2) / 8.0)] * 2)
    assert describe(evening) == "evening peak"
    assert describe(np.ones(96)) == "flat"
    night = np.concatenate([np.where(slots < 12, 1.6, 0.8)] * 2)
    assert describe(night) == "night heavy"


def test_matched_households_never_include_dtou_and_stay_in_cluster() -> None:
    treated = pl.DataFrame(
        {
            "household": ["T1", "T2", "T3"],
            "tariff": ["ToU"] * 3,
            "pre_mean_kwh": [0.2, 0.4, 0.3],
            "cluster": [0, 0, 1],
        }
    )
    pool = pl.DataFrame(
        {
            "household": ["S1", "S2", "S3", "S4"],
            "tariff": ["Std"] * 4,
            "pre_mean_kwh": [0.21, 0.39, 0.25, 0.9],
            "cluster": [0, 0, 1, 2],
        }
    )
    pairs, dropped = match_households(treated, pool)
    assert dropped == 0
    assert set(pairs["control"].to_list()) <= set(pool["household"].to_list())
    assert not set(pairs["control"].to_list()) & set(treated["household"].to_list())
    by = dict(zip(pairs["treated"].to_list(), pairs["control"].to_list(), strict=True))
    assert by == {"T1": "S1", "T2": "S2", "T3": "S3"}
    assert pairs["control"].n_unique() == pairs.height, "without replacement"
    short_pool = pool.filter(pl.col("household") != "S3")
    _, dropped = match_households(treated, short_pool)
    assert dropped == 1
    with pytest.raises(ValueError):
        match_households(pool.with_columns(pl.lit("Std").alias("tariff")), pool)


def _tariff() -> pl.DataFrame:
    start = datetime(2013, 1, 1)
    ts = [start + HALF_HOUR * i for i in range(48 * 60)]
    band = ["Normal"] * len(ts)
    # Two events: a six half hour evening event on day 3 and a twelve half hour morning event on day 20.
    for i in range(48 * 3 + 34, 48 * 3 + 40):
        band[i] = "High"
    for i in range(48 * 20 + 12, 48 * 20 + 24):
        band[i] = "High"
    return pl.DataFrame({"ts": ts, "band": band})


def test_high_price_events_are_maximal_runs_with_types() -> None:
    events = high_price_events(_tariff())
    assert [e.half_hours for e in events] == [6, 12]
    assert [e.event_type for e in events] == ["evening", "morning"]
    assert events[0].start == datetime(2013, 1, 4, 17, 0) and events[0].end == datetime(2013, 1, 4, 19, 30)
    with pytest.raises(ValueError):
        high_price_events(_tariff().head(0))


def test_slot_table_uses_same_daytype_comparison_days_without_high_bands() -> None:
    tariff = _tariff()
    events = high_price_events(tariff)
    slots = slot_table(events, tariff)
    first = slots.filter((pl.col("event_id") == 0) & (pl.col("role") == "event"))
    assert first.height == 6
    comparison = slots.filter((pl.col("event_id") == 0) & (pl.col("role") == "event_comparison"))
    days = comparison["day"].unique().to_list()
    assert all((d.weekday() >= 5) == (events[0].daytype == "weekend") for d in days)
    high = set(tariff.filter(pl.col("band") == "High")["ts"].to_list())
    assert not set(comparison["ts"].to_list()) & high
    rebound = slots.filter((pl.col("event_id") == 0) & (pl.col("role") == "rebound"))
    assert rebound.height == PLAN.rebound_hours * 2
    assert rebound["ts"].min() == events[0].end + HALF_HOUR


def test_analyse_recovers_a_planted_response() -> None:
    tariff = _tariff()
    events = high_price_events(tariff)
    pairs = pl.DataFrame(
        {
            "treated": [f"T{i}" for i in range(20)],
            "control": [f"C{i}" for i in range(20)],
            "cluster": [0] * 20,
        }
    )
    rows = []
    for e in events:
        for i in range(20):
            base_t, base_c = 0.30 + 0.001 * i, 0.30 + 0.001 * i
            rows.append((f"T{i}", e.event_id, "event", base_t * 0.8, 6, 1))
            rows.append((f"T{i}", e.event_id, "event_comparison", base_t, 60, 10))
            rows.append((f"C{i}", e.event_id, "event", base_c, 6, 1))
            rows.append((f"C{i}", e.event_id, "event_comparison", base_c, 60, 10))
            rows.append((f"T{i}", e.event_id, "rebound", base_t * 1.1, 6, 1))
            rows.append((f"T{i}", e.event_id, "rebound_comparison", base_t, 60, 10))
            rows.append((f"C{i}", e.event_id, "rebound", base_c, 6, 1))
            rows.append((f"C{i}", e.event_id, "rebound_comparison", base_c, 60, 10))
    consumption = pl.DataFrame(
        rows, schema=["household", "event_id", "role", "kwh", "n", "days"], orient="row"
    )
    result = analyse(consumption, pairs, events, seed=1)
    assert result.events == 2 and result.pairs == 20
    assert abs(result.overall_pct - (-0.2)) < 1e-9
    assert abs(result.rebound_pct - 0.1) < 1e-9
    assert result.by_type.height == 4
    assert result.by_type.filter(pl.col("event_type") == "night")["events"][0] == 0
    with pytest.raises(ValueError):
        analyse(consumption, pairs.with_columns(pl.col("treated").alias("control")), events, seed=1)


def test_plan_hash_in_the_results_equals_the_committed_plan() -> None:
    path = ROOT / "results" / "meter" / "plan.json"
    if not path.exists():
        pytest.skip("results/meter/plan.json is not there yet; run `lookahead meter`")
    recorded = json.loads(path.read_text(encoding="utf-8"))["sha256"]
    assert recorded == plan_hash(ROOT / "docs" / "tou_plan.md")


def test_cluster_panel_total_is_the_sum_of_the_clusters() -> None:
    ts = [datetime(2013, 1, 1) + timedelta(hours=h) for h in range(48)]
    loads = pl.concat(
        [
            pl.DataFrame({"cluster": [c] * 48, "ts": ts, "kwh": [float(c + 1)] * 48, "households": [10] * 48})
            for c in range(3)
        ]
    )
    panel = cluster_panel(loads)
    total = panel.filter(pl.col("authority") == TOTAL)["demand"].to_list()
    assert total == [6.0] * 48
    assert set(panel["authority"].unique().to_list()) == {"0", "1", "2", TOTAL}
    summing = summing_for(["0", "1", "2"])
    assert summing.nodes[0] == TOTAL and len(summing.leaves) == 3
    windows = meter_windows(datetime(2014, 2, 28))
    assert windows["test_start"] == "2013-12-01" and windows["test_end"] == "2014-02-28"
    assert windows["validation_start"] == "2012-12-01"
