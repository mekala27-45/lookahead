"""Stage: the meter. Load shape clusters, the pre-registered time of use analysis, the cluster
forecast reconciled to the panel total, and the peak contribution table.

Reads the London release through DuckDB (data/external/london/readings.parquet, never
committed) and writes cluster level and event level tables only: no household identifier is
written under results/. Writes results/meter/*.parquet, plan.json and
results/manifests/meter.json.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import numpy as np
import polars as pl
from lookahead_contracts.london import read_tariffs
from lookahead_core.config import POLICY
from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths
from lookahead_meter.clusters import cluster_households, peak_shares
from lookahead_meter.forecast import cluster_panel, forecast_and_reconcile, meter_windows
from lookahead_meter.plan import PLAN, plan_hash
from lookahead_meter.queries import (
    connect,
    hourly_cluster_loads,
    households_covering,
    pre_period_means,
    profiles,
    slot_consumption,
)
from lookahead_meter.tou import analyse, high_price_events, match_households, slot_table

RELEASE_LAST_HOUR = datetime(2014, 2, 28, 0, 0)
"""The last reading in the release is at 2014-02-28 00:00."""
FORECAST_PANEL_START = "2012-09-01"
FORECAST_PANEL_END = "2014-02-28"
FORECAST_PANEL_MIN_SHARE = 0.95


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    started = time.time()
    folder = paths.results / "meter"
    folder.mkdir(parents=True, exist_ok=True)
    external = paths.data / "external" / "london"
    con = connect(external / "readings.parquet")
    manifest = Manifest(as_of=as_of, seed=seed)

    # 1. Profiles over the year before the test period, and the clusters.
    windows = meter_windows(RELEASE_LAST_HOUR)
    profile_end = str(windows["test_start"])
    profile_start = (
        (datetime.fromisoformat(profile_end) - timedelta(days=POLICY.meter_profile_window_days))
        .date()
        .isoformat()
    )
    prof = profiles(con, profile_start, profile_end)
    clustering = cluster_households(prof, seed)
    shares = peak_shares(prof, clustering.assignment)
    centroids = pl.DataFrame(
        {
            "cluster": np.repeat(np.arange(clustering.k), 96),
            "daytype": np.tile(np.array(["weekday"] * 48 + ["weekend"] * 48), clustering.k),
            "slot": np.tile(np.arange(96) % 48, clustering.k),
            "ratio": clustering.centroids.reshape(-1),
        }
    )
    centroids.write_parquet(folder / "cluster_profiles.parquet")
    cluster_table = shares.with_columns(
        pl.col("cluster")
        .map_elements(lambda c: clustering.labels[int(c)], return_dtype=pl.Utf8)
        .alias("shape")
    )
    tariff_mix = (
        clustering.assignment.group_by("cluster")
        .agg((pl.col("tariff") == "ToU").mean().alias("dtou_share"))
        .sort("cluster")
    )
    cluster_table = cluster_table.join(tariff_mix, on="cluster", how="left").sort("cluster")
    cluster_table.write_parquet(folder / "clusters.parquet")
    w = Scribe(
        manifest,
        source="real:london",
        model="none",
        population=f"{clustering.households} households with a full profile over the year before the test period",
        origin="lookahead_registry.stages.meter",
    )
    w.put("meter.households_release", int(prof["household"].n_unique()), "int")
    w.put("meter.households_profiled", clustering.households, "int")
    w.put("meter.clusters", clustering.k, "int")
    w.put("meter.cluster_validation_households", clustering.validation_households, "int")
    w.put("meter.profile_window_start", profile_start, "text")
    w.put("meter.profile_window_end", profile_end, "text")
    best_sil = clustering.silhouette_by_k[clustering.k]
    w.put("meter.silhouette_chosen", best_sil, "float3")
    w.table(
        "meter.silhouette_by_k",
        ["Clusters", "Validation silhouette"],
        ["int", "float3"],
        [[k, v] for k, v in sorted(clustering.silhouette_by_k.items())],
    )
    w.table(
        "meter.clusters",
        ["Cluster", "Shape", "Households", "Mean kWh per half hour", "Share of evening peak", "dToU share"],
        ["int", "text", "int", "float3", "pct1", "pct1"],
        [
            [
                r["cluster"],
                r["shape"],
                r["households"],
                r["mean_kwh"],
                r["evening_peak_share"],
                r["dtou_share"],
            ]
            for r in cluster_table.iter_rows(named=True)
        ],
    )
    top = cluster_table.sort("evening_peak_share", descending=True).head(1)
    w.put("meter.top_peak_cluster", int(top["cluster"][0]), "int")
    w.put("meter.top_peak_cluster_shape", str(top["shape"][0]), "text")
    w.put("meter.top_peak_cluster_share", float(top["evening_peak_share"][0]), "pct1")
    w.put(
        "meter.top_peak_cluster_household_share", float(top["households"][0]) / clustering.households, "pct1"
    )
    for r in cluster_table.iter_rows(named=True):
        w.put(f"meter.cluster.{r['cluster']}.shape", str(r["shape"]), "text")
        w.put(f"meter.cluster.{r['cluster']}.peak_share", float(r["evening_peak_share"]), "pct1")
        w.put(f"meter.cluster.{r['cluster']}.households", int(r["households"]), "int")

    # 2. The time of use analysis, as pre-registered.
    plan_path = paths.root / "docs" / "tou_plan.md"
    digest = plan_hash(plan_path)
    tariff = read_tariffs(external)
    events = high_price_events(tariff)
    pre = pre_period_means(con, PLAN.pre_period_start, PLAN.pre_period_end)
    covering_2013 = households_covering(con, "2013-01-01", "2014-01-01", 0.5).select("household")
    eligible = (
        pre.join(covering_2013, on="household", how="inner")
        .join(clustering.assignment.select("household", "cluster"), on="household", how="inner")
        .sort("household")
    )
    treated = eligible.filter(pl.col("tariff") == "ToU")
    pool = eligible.filter(pl.col("tariff") == "Std")
    pairs, dropped = match_households(treated, pool)
    slots = slot_table(events, tariff)
    wanted = pl.concat(
        [
            pairs.select(pl.col("treated").alias("household")),
            pairs.select(pl.col("control").alias("household")),
        ]
    )
    consumption = slot_consumption(con, wanted, slots)
    tou = analyse(consumption, pairs, events, seed)
    tou.dropped = dropped
    tou.plan_hash = digest
    (folder / "plan.json").write_text(
        json.dumps(
            {
                "plan": "docs/tou_plan.md",
                "sha256": digest,
                "events": tou.events,
                "treated": tou.treated,
                "pairs": tou.pairs,
                "dropped": dropped,
                "replicates": tou.replicates,
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    tou.per_event.select(
        "event_id",
        "event_type",
        "half_hours",
        "start",
        "pairs",
        "did_kwh",
        "control_event_kwh",
        "response_pct",
        "rebound_kwh",
        "rebound_pct",
        "did_kwh_per_event",
    ).write_parquet(folder / "tou_events.parquet")
    tou.by_type.write_parquet(folder / "tou_by_type.parquet")
    w = Scribe(
        manifest,
        source="real:london",
        model="none",
        population=f"{tou.pairs} matched pairs over {tou.events} high price events of 2013",
        origin="lookahead_registry.stages.meter",
        seeds=tou.replicates,
    )
    w.put("meter.tou.plan_hash", digest, "text")
    w.put("meter.tou.plan_hash_short", digest[:12], "text")
    w.put("meter.tou.events", tou.events, "int")
    w.put("meter.tou.dtou_households", int((eligible["tariff"] == "ToU").sum()), "int")
    w.put("meter.tou.std_pool", int((eligible["tariff"] == "Std").sum()), "int")
    w.put("meter.tou.pairs", tou.pairs, "int")
    w.put("meter.tou.dropped", dropped, "int")
    w.put("meter.tou.response_pct", tou.overall_pct, "spct1")
    w.put("meter.tou.response_pct_lower", tou.overall_pct_lower, "spct1")
    w.put("meter.tou.response_pct_upper", tou.overall_pct_upper, "spct1")
    w.put("meter.tou.response_kwh", tou.overall_kwh, "float3")
    w.put("meter.tou.response_kwh_lower", tou.overall_kwh_lower, "float3")
    w.put("meter.tou.response_kwh_upper", tou.overall_kwh_upper, "float3")
    w.put("meter.tou.rebound_pct", tou.rebound_pct, "spct1")
    w.put("meter.tou.rebound_pct_lower", tou.rebound_pct_lower, "spct1")
    w.put("meter.tou.rebound_pct_upper", tou.rebound_pct_upper, "spct1")
    w.put("meter.tou.replicates", tou.replicates, "int")
    w.put("meter.tou.types_rejected", int(tou.by_type["rejected"].sum()), "int")
    w.put("meter.tou.types", tou.by_type.height, "int")
    w.table(
        "meter.tou.by_type",
        ["Event type", "Events", "Response", "lower", "upper", "p value", "After correction"],
        ["text", "int", "spct1", "spct1", "spct1", "float3", "text"],
        [
            [
                r["event_type"],
                r["events"],
                r["response_pct"],
                r["lower"],
                r["upper"],
                r["p_value"],
                "different from zero" if r["rejected"] else "not distinguishable from zero",
            ]
            for r in tou.by_type.iter_rows(named=True)
        ],
    )
    mean_event_hours = float(str(tou.per_event["half_hours"].mean())) / 2.0
    w.put("meter.tou.mean_event_hours", mean_event_hours, "float1")

    # 3. The cluster forecast reconciled to the panel total.
    fixed = households_covering(con, FORECAST_PANEL_START, FORECAST_PANEL_END, FORECAST_PANEL_MIN_SHARE)
    assignment = fixed.select("household").join(
        clustering.assignment.select("household", "cluster"), on="household", how="inner"
    )
    loads = hourly_cluster_loads(con, assignment, FORECAST_PANEL_START, "2014-03-01")
    panel = cluster_panel(loads)
    forecast = forecast_and_reconcile(panel, windows, seed)
    forecast.scores.write_parquet(folder / "forecast_scores.parquet")
    forecast.reconciled_total.write_parquet(folder / "forecast_total.parquet")
    base = forecast.scores.filter(pl.col("method") == "base")
    mint = forecast.scores.filter(pl.col("method") == "mint")
    w = Scribe(
        manifest,
        source="real:london",
        model="gbm",
        population=f"{assignment.height} households reporting through the whole forecast window, {forecast.origins} origins",
        origin="lookahead_registry.stages.meter",
    )
    w.put("meter.forecast.households", assignment.height, "int")
    w.put("meter.forecast.household_share", assignment.height / clustering.households, "pct0")
    w.put("meter.forecast.origins", forecast.origins, "int")
    w.put("meter.forecast.fits", forecast.fits, "int")
    w.put("meter.forecast.rows", forecast.rows, "int")
    w.put("meter.forecast.test_start", str(windows["test_start"]), "text")
    w.put("meter.forecast.test_end", str(windows["test_end"]), "text")
    w.put("meter.forecast.shrinkage_intensity", forecast.shrinkage_intensity, "float2")
    for method, gap in forecast.coherence_gap.items():
        w.put(f"meter.forecast.coherence_gap.{method}", gap, "float6")
    rows: list[list[Scalar]] = []
    for r in forecast.scores.sort(["level", "method"]).iter_rows(named=True):
        rows.append([r["level_name"], r["method"], r["mape"], r["lower"], r["upper"], r["coverage_90"]])
    w.table(
        "meter.forecast.by_level",
        ["Level", "Method", "MAPE", "lower", "upper", "90 pct coverage"],
        ["text", "text", "pct2", "pct2", "pct2", "pct1"],
        rows,
    )
    for r in forecast.scores.iter_rows(named=True):
        w.put(f"meter.forecast.{r['method']}.level{r['level']}.mape", r["mape"], "pct2")
        w.put(f"meter.forecast.{r['method']}.level{r['level']}.mape_lower", r["lower"], "pct2")
        w.put(f"meter.forecast.{r['method']}.level{r['level']}.mape_upper", r["upper"], "pct2")
        w.put(f"meter.forecast.{r['method']}.level{r['level']}.coverage_90", r["coverage_90"], "pct1")
    base_total = float(base.filter(pl.col("level") == 0)["mape"][0])
    mint_total = float(mint.filter(pl.col("level") == 0)["mape"][0])
    base_leaves = float(base.filter(pl.col("level") == 1)["mape"][0])
    mint_leaves = float(mint.filter(pl.col("level") == 1)["mape"][0])
    w.put("meter.forecast.mint_gain_total", base_total - mint_total, "spct2")
    w.put("meter.forecast.mint_gain_clusters", base_leaves - mint_leaves, "spct2")
    w.put("meter.forecast.mint_verdict_total", "helped" if mint_total < base_total else "hurt", "text")
    w.put("meter.forecast.mint_verdict_clusters", "helped" if mint_leaves < base_leaves else "hurt", "text")

    # 4. Peak contribution: what a demand response program would target first.
    value = POLICY.peak_reduction_value_gbp_per_kw
    evening = prof.filter((pl.col("daytype") == "weekday") & pl.col("slot").is_in([34, 35, 36, 37, 38, 39]))
    per_cluster = (
        evening.join(clustering.assignment.select("household", "cluster"), on="household", how="inner")
        .group_by("cluster")
        .agg(
            pl.col("kwh").mean().alias("evening_kwh_per_half_hour"),
            pl.col("household").n_unique().alias("households"),
        )
        .sort("cluster")
    )
    contribution = per_cluster.with_columns(
        (pl.col("evening_kwh_per_half_hour") * 2.0).alias("evening_kw_per_household"),
        (pl.col("evening_kwh_per_half_hour") * 2.0 * pl.col("households")).alias("evening_kw"),
    )
    total_kw = float(contribution["evening_kw"].sum())
    contribution = contribution.with_columns(
        (pl.col("evening_kw") / total_kw).alias("share"),
        (pl.col("evening_kw_per_household") * 0.1 * value).alias("value_gbp_per_household_10pct"),
    ).join(cluster_table.select("cluster", "shape"), on="cluster", how="left")
    contribution.write_parquet(folder / "peak_contribution.parquet")
    w.put("meter.peak.value_gbp_per_kw", value, "float0")
    w.put("meter.peak.total_kw", total_kw, "float0")
    w.table(
        "meter.peak.contribution",
        [
            "Cluster",
            "Shape",
            "Households",
            "Evening kW per household",
            "Share of the evening peak",
            "Value of a 10 pct cut, GBP per household",
        ],
        ["text", "text", "int", "float2", "pct1", "float1"],
        [
            [
                str(r["cluster"]),
                r["shape"],
                r["households"],
                r["evening_kw_per_household"],
                r["share"],
                r["value_gbp_per_household_10pct"],
            ]
            for r in contribution.sort("share", descending=True).iter_rows(named=True)
        ],
    )
    first = contribution.sort("evening_kw_per_household", descending=True).head(1)
    w.put("meter.peak.target_cluster", str(first["cluster"][0]), "text")
    w.put("meter.peak.target_shape", str(first["shape"][0]), "text")
    w.put("meter.peak.target_kw_per_household", float(first["evening_kw_per_household"][0]), "float2")
    w.put("meter.seconds", time.time() - started, "float1")
    con.close()
    manifest.save(paths.results / "manifests" / "meter.json")
    return manifest
