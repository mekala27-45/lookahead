"""Stage: the marts the control room queries in the browser, and its bundle.

Everything the site draws that is not a manifest value is a small parquet file under
web/public/data, written here from the results the earlier stages produced, plus bundle.json
(the authorities, the regions, the tile positions, the policy, the file list with byte sizes so
the reader never needs a HEAD request) and a copy of the merged manifest. No household
identifier and no prediction frame at full size goes in.
"""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from lookahead_core.config import INTERCONNECTIONS, POLICY, REGION_LABELS, REGIONS
from lookahead_core.manifest import Manifest
from lookahead_core.paths import Paths
from lookahead_core.statements import STATEMENT
from lookahead_evaluation.metrics import row_errors

from lookahead_registry.stages.data import load_hierarchy, load_panel


def _served_backend(paths: Paths) -> str:
    path = paths.results / "registry" / "served.json"
    if path.exists():
        return str(json.loads(path.read_text(encoding="utf-8")).get("backend", "own"))
    return "own"


def _interconnection(region: str) -> str:
    for name, members in INTERCONNECTIONS.items():
        if region in members:
            return name
    return "unknown"


def _write(frame: pl.DataFrame, folder: Path, name: str) -> None:
    frame.write_parquet(folder / f"{name}.parquet", compression="zstd")


def _scoring(paths: Paths, backend: str) -> pl.DataFrame | None:
    path = paths.results / "backtest" / backend / "scoring.parquet"
    return pl.read_parquet(path) if path.exists() else None


def _fan_latest(scoring: pl.DataFrame) -> pl.DataFrame:
    """The last origin's 48 rows per authority, with the actual, the operator and the naive."""
    last = scoring.group_by("authority").agg(pl.col("origin").max().alias("origin"))
    return (
        scoring.join(last, on=["authority", "origin"], how="inner")
        .select(
            "authority",
            "origin",
            "horizon",
            "target_hour",
            "q05",
            "q25",
            "q50",
            "q75",
            "q95",
            "actual",
            "operator",
            "naive",
        )
        .sort(["authority", "horizon"])
    )


def _horizon_profile(scoring: pl.DataFrame) -> pl.DataFrame:
    errors = row_errors(scoring)
    return (
        errors.group_by(["authority", "horizon"])
        .agg(
            pl.col("ape_model").mean().alias("mape_model"),
            pl.col("ape_operator").filter(pl.col("has_operator") == 1.0).mean().alias("mape_operator"),
            pl.col("ape_naive").mean().alias("mape_naive"),
            pl.col("in90").mean().alias("coverage_90"),
            pl.col("in50").mean().alias("coverage_50"),
            pl.len().alias("rows"),
        )
        .sort(["authority", "horizon"])
    )


def _latest_error(scoring: pl.DataFrame) -> pl.DataFrame:
    """The signed error of the served forecast over the last origin's first day, per authority: what
    the tile map is colored by. Positive means the forecast ran over the actual."""
    last = scoring.group_by("authority").agg(pl.col("origin").max().alias("origin"))
    rows = scoring.join(last, on=["authority", "origin"], how="inner").filter(
        (pl.col("horizon") <= 24) & pl.col("actual").is_not_null() & (pl.col("actual") > 0)
    )
    return rows.group_by("authority").agg(
        ((pl.col("q50") - pl.col("actual")) / pl.col("actual")).mean().alias("latest_error"),
        pl.col("origin").first().alias("latest_origin"),
        pl.len().alias("latest_hours"),
    )


def _by_authority(scoring: pl.DataFrame) -> pl.DataFrame:
    errors = row_errors(scoring)
    short = errors.filter(pl.col("horizon") <= 24)
    return short.group_by("authority").agg(
        pl.col("ape_model").mean().alias("mape_h1_24"),
        pl.col("ape_operator").filter(pl.col("has_operator") == 1.0).mean().alias("operator_mape_h1_24"),
        pl.col("ape_naive").mean().alias("naive_mape_h1_24"),
        pl.col("in90").mean().alias("coverage_90"),
        pl.col("in50").mean().alias("coverage_50"),
        pl.col("crps").mean().alias("crps"),
        pl.len().alias("hours"),
    )


def _reliability(scoring: pl.DataFrame, backend: str) -> pl.DataFrame:
    rows = []
    ok = scoring.filter(pl.col("actual").is_not_null() & pl.col("q50").is_not_null())
    for level, column in zip(POLICY_LEVELS, ("q05", "q25", "q50", "q75", "q95"), strict=True):
        for bucket, (lo, hi) in {"h1_24": (1, 24), "h25_48": (25, 48), "all": (1, 48)}.items():
            sub = ok.filter((pl.col("horizon") >= lo) & (pl.col("horizon") <= hi))
            share = float(str((sub["actual"] <= sub[column]).mean())) if sub.height else float("nan")
            rows.append(
                {
                    "backend": backend,
                    "bucket": bucket,
                    "level": level,
                    "share_below": share,
                    "rows": sub.height,
                }
            )
    return pl.DataFrame(rows)


POLICY_LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    folder = paths.root / "web" / "public" / "data"
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.parquet"):
        old.unlink()
    served = _served_backend(paths)
    authorities_table = pl.read_csv(paths.eia / "authorities.csv")
    eligible = authorities_table.filter(pl.col("backtest_eligible"))
    hierarchy = load_hierarchy(paths)
    tiles = pl.read_csv(paths.data / "tiles.csv")

    # 1. Backtest marts for every backend that ran; the tile map and the fans from the served one.
    scorings: dict[str, pl.DataFrame] = {}
    for backend in ("own", "gbm", "seasonal_naive"):
        s = _scoring(paths, backend)
        if s is not None:
            scorings[backend] = s
    if served not in scorings:
        served = "own" if "own" in scorings else next(iter(scorings), "own")
    fans = []
    profiles = []
    by_authority = []
    reliability = []
    for backend, s in scorings.items():
        fans.append(_fan_latest(s).with_columns(pl.lit(backend).alias("backend")))
        profiles.append(_horizon_profile(s).with_columns(pl.lit(backend).alias("backend")))
        by_authority.append(_by_authority(s).with_columns(pl.lit(backend).alias("backend")))
        if backend != "seasonal_naive":
            reliability.append(_reliability(s, backend))
    if fans:
        _write(pl.concat(fans), folder, "fan_latest")
        _write(pl.concat(profiles), folder, "horizon_profile")
        _write(pl.concat(by_authority), folder, "backtest_by_authority")
    if reliability:
        _write(pl.concat(reliability), folder, "reliability")

    # Tiles: position, region, latest error of the served backend, skill verdict.
    latest = (
        _latest_error(scorings[served])
        if served in scorings
        else pl.DataFrame({"authority": [], "latest_error": [], "latest_origin": [], "latest_hours": []})
    )
    skill_path = paths.results / "skill" / "skill_rows.parquet"
    skill = pl.read_parquet(skill_path) if skill_path.exists() else None
    tile_frame = tiles.join(
        authorities_table.select("authority", "region", "operator_comparable", "backtest_eligible"),
        on="authority",
        how="left",
    )
    tile_frame = tile_frame.join(latest, on="authority", how="left")
    if skill is not None:
        verdicts = skill.filter((pl.col("backend") == served) & (pl.col("band") == "h1_24")).select(
            "authority", pl.col("skill").alias("skill_h1_24"), pl.col("verdict")
        )
        tile_frame = tile_frame.join(verdicts, on="authority", how="left")
    else:
        tile_frame = tile_frame.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("skill_h1_24"), pl.lit(None, dtype=pl.Utf8).alias("verdict")
        )
    _write(tile_frame.with_columns(pl.lit(served).alias("backend")), folder, "tiles")
    if skill is not None:
        _write(skill, folder, "skill_rows")

    # 2. The other stages' tables, when they have run.
    def copy_if(rel: str, name: str) -> None:
        path = paths.results / rel
        if path.exists():
            frame = pl.read_parquet(path) if path.suffix == ".parquet" else pl.read_csv(path)
            _write(frame, folder, name)

    copy_if("recovery/summary.parquet", "recovery")
    copy_if("hierarchy/scores_by_level.parquet", "hierarchy_levels")
    copy_if("hierarchy/scores_by_node.parquet", "hierarchy_nodes")
    copy_if("events/alerts.parquet", "events_alerts")
    copy_if("events/known_events.parquet", "known_events")
    copy_if("events/by_authority.parquet", "events_by_authority")
    copy_if("meter/clusters.parquet", "meter_clusters")
    copy_if("meter/cluster_profiles.parquet", "meter_profiles")
    copy_if("meter/tou_by_type.parquet", "tou_by_type")
    copy_if("meter/tou_events.parquet", "tou_events")
    copy_if("meter/forecast_scores.parquet", "meter_forecast_scores")
    copy_if("meter/forecast_total.parquet", "meter_forecast_total")
    copy_if("meter/peak_contribution.parquet", "peak_contribution")
    if (paths.results / "hierarchy" / "reconciled.parquet").exists():
        reconciled = pl.read_parquet(paths.results / "hierarchy" / "reconciled.parquet")
        # The lower 48 fan for the front page: the last origin's 48 hours, base and reconciled.
        top = reconciled.filter(pl.col("node") == "US48")
        last_origin = top["origin"].max()
        _write(
            top.filter(pl.col("origin") == last_origin).sort(["method", "horizon"]), folder, "lower48_latest"
        )
        # Per authority the reconciled and base median at the last origin, for the authority page.
        auth_nodes = hierarchy.filter(pl.col("level") == 3)["node"].to_list()
        per_auth = reconciled.filter(pl.col("node").is_in(auth_nodes) & (pl.col("origin") == last_origin))
        _write(per_auth.sort(["node", "method", "horizon"]), folder, "reconciled_latest")
    if (paths.results / "events" / "residuals.parquet").exists():
        residuals = pl.read_parquet(paths.results / "events" / "residuals.parquet")
        heat = (
            residuals.filter(pl.col("z").is_not_null())
            .with_columns(
                pl.col("utc_hour").dt.date().alias("day"),
                pl.col("utc_hour").dt.hour().alias("hour"),
                pl.col("z").cast(pl.Float32).alias("z"),
            )
            .select("authority", "day", "hour", "z")
        )
        _write(heat, folder, "residual_heatmap")
    if (paths.results / "events" / "known_event_windows.parquet").exists():
        windows = pl.read_parquet(paths.results / "events" / "known_event_windows.parquet")
        _write(windows.with_columns(pl.col("z").cast(pl.Float32)), folder, "known_event_windows")

    # 3. The weather driver for the authority pages: the last three weeks of temperature with the
    # thresholds the own backend chose.
    weather = pl.read_parquet(paths.weather / "hourly.parquet")
    last_hour = weather["utc_hour"].max()
    assert isinstance(last_hour, datetime)
    recent = weather.filter(pl.col("utc_hour") > last_hour - pl.duration(days=21)).select(
        "authority", "utc_hour", "temperature_c", "humidity_pct"
    )
    export = paths.results / "models" / "own_model.json"
    thresholds = pl.DataFrame(
        {"authority": [], "heating_threshold_c": [], "cooling_threshold_c": []},
        schema={"authority": pl.Utf8, "heating_threshold_c": pl.Float64, "cooling_threshold_c": pl.Float64},
    )
    if export.exists():
        payload = json.loads(export.read_text(encoding="utf-8"))
        thresholds = pl.DataFrame(
            {
                "authority": list(payload["authorities"]),
                "heating_threshold_c": [
                    float(a["heating_threshold_c"]) for a in payload["authorities"].values()
                ],
                "cooling_threshold_c": [
                    float(a["cooling_threshold_c"]) for a in payload["authorities"].values()
                ],
            }
        )
    _write(recent.join(thresholds, on="authority", how="left"), folder, "weather_recent")

    # 4. The bundle and the manifest copy.
    panel_authorities = eligible["authority"].to_list()
    typical = (
        load_panel(paths)
        .filter(pl.col("authority").is_in(panel_authorities))
        .group_by("authority")
        .agg(pl.col("demand").mean().alias("typical_mw"))
    )
    authorities = (
        eligible.select("authority", "region", "operator_comparable")
        .join(typical, on="authority", how="left")
        .sort("authority")
    )
    known_path = paths.data / "known_events.csv"
    known = (
        pl.read_csv(known_path).select("event", "node", "onset_utc", "end_utc", "description").to_dicts()
        if known_path.exists()
        else []
    )
    files = sorted(p.name for p in folder.glob("*.parquet"))
    bundle: dict[str, Any] = {
        "statement": STATEMENT,
        "as_of": as_of,
        "built_at": datetime.now(UTC).isoformat(),
        "served_backend": served,
        "backends": sorted(scorings),
        "authorities": [
            {
                "authority": r["authority"],
                "region": r["region"],
                "label": r["authority"],
                "interconnection": _interconnection(str(r["region"])),
                "comparable": bool(r["operator_comparable"]),
                "typical_mw": float(r["typical_mw"]) if r["typical_mw"] is not None else 0.0,
            }
            for r in authorities.iter_rows(named=True)
        ],
        "regions": [
            {"code": r, "label": REGION_LABELS[r], "interconnection": _interconnection(r)} for r in REGIONS
        ],
        "tiles": tiles.select("authority", "region", "row", "col").to_dicts(),
        "policy": {
            "issue_hour_utc": POLICY.issue_hour_utc,
            "horizons": POLICY.horizons,
            "quantile_levels": list(POLICY_LEVELS),
            "interval_level": POLICY.interval_level,
            "alert_persistence_hours": POLICY.alert_persistence_hours,
        },
        "known_events": known,
        "files": files,
        "bytes": {name: (folder / name).stat().st_size for name in files},
    }
    (folder / "bundle.json").write_text(json.dumps(bundle, indent=1, default=str) + "\n", encoding="utf-8")
    if paths.manifest.exists():
        shutil.copyfile(paths.manifest, folder / "manifest.json")
    for name in ("live_check.json",):
        src = paths.results / name
        if src.exists():
            shutil.copyfile(src, folder / name)
    manifest = Manifest(as_of=as_of, seed=seed)
    manifest.put(
        "marts.files",
        len(files),
        "int",
        source="static",
        population="web/public/data",
        origin="lookahead_registry.stages.marts",
    )
    manifest.put(
        "marts.bytes",
        float(sum(bundle["bytes"].values())),
        "float0",
        source="static",
        population="web/public/data",
        origin="lookahead_registry.stages.marts",
    )
    _ = np
    return manifest
