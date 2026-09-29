"""Stage: hourly weather per authority location, from the Open-Meteo cache, committed as parquet.

Reads data/locations.csv and data/eia930/authorities.csv (the demand reporters), pulls any
missing (authority, year) into data/external/weather when the host is reachable, and writes
data/weather/hourly.parquet with the attribution beside it. Writes results/manifests/weather.json.
"""

from __future__ import annotations

from datetime import date

import httpx
import polars as pl
from lookahead_core.manifest import Manifest, Scribe
from lookahead_core.paths import Paths
from lookahead_weather import pulls

from lookahead_registry.stages.data import load_windows


def run(paths: Paths, as_of: str, seed: int, *, attempt_pull: bool = True) -> Manifest:
    locations = pl.read_csv(paths.data / "locations.csv")
    authorities = pl.read_csv(paths.eia / "authorities.csv")
    reporters = authorities.filter(pl.col("reports_demand"))["authority"].to_list()
    missing_locations = sorted(set(reporters) - set(locations["authority"].to_list()))
    if missing_locations:
        raise FileNotFoundError(
            f"data/locations.csv has no row for the demand reporting authorities {missing_locations}"
        )
    # Weather is pulled for the authorities in the backtest: every one with a full validation and test year.
    eligible = authorities.filter(pl.col("backtest_eligible"))["authority"].to_list()
    chosen = locations.filter(pl.col("authority").is_in(eligible)).sort("authority")
    windows = load_windows(paths)
    first = date.fromisoformat(str(windows["training_start"]))
    last = min(date.fromisoformat(str(windows["test_end"])), pulls.last_archived_day())
    cache = paths.external / "weather"
    client: httpx.Client | None = None
    if attempt_pull:
        try:
            probe = httpx.Client(timeout=20.0)
            probe.get(
                pulls.ARCHIVE_URL,
                params={
                    "latitude": "40.7",
                    "longitude": "-74.0",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-01",
                    "hourly": "temperature_2m",
                },
            )
            client = probe
        except httpx.HTTPError:
            client = None
    pulls.ensure_cache(chosen, cache, first, last, client)
    weather = pulls.assemble(chosen, cache, first, last)
    paths.weather.mkdir(parents=True, exist_ok=True)
    weather.write_parquet(paths.weather / "hourly.parquet", compression="zstd")
    (paths.weather / "ATTRIBUTION.md").write_text(
        "# Weather attribution\n\n"
        + pulls.ATTRIBUTION
        + "\n\nOne location per balancing authority, listed with its reason in data/locations.csv.\n",
        encoding="utf-8",
    )
    manifest = Manifest(as_of=as_of, seed=seed)
    w = Scribe(
        manifest,
        source="real:open_meteo",
        population="one location per demand reporting authority",
        origin="lookahead_registry.stages.weather",
    )
    w.put("data.weather.authorities", chosen.height, "int")
    w.put(
        "data.weather.reporters_without_weather",
        ", ".join(sorted(set(reporters) - set(eligible))) or "none",
        "text",
    )
    w.put("data.weather.rows", weather.height, "int")
    w.put("data.weather.first_hour", str(weather["utc_hour"].min()), "text")
    w.put("data.weather.last_hour", str(weather["utc_hour"].max()), "text")
    w.put("data.weather.null_temperatures", int(weather["temperature_c"].null_count()), "int")
    w.put("data.weather.pulls_cached", len(list(cache.glob("*.json"))), "int")
    w.put(
        "data.weather.pulled_this_run",
        "yes" if client is not None else "no, the cache was complete or the host unreachable",
        "text",
    )
    rows = [
        [
            r["authority"],
            f"{r['name']}, {r['state']}",
            float(r["latitude"]),
            float(r["longitude"]),
            r["reason"],
        ]
        for r in chosen.iter_rows(named=True)
    ]
    w.table(
        "data.weather.locations",
        ["Authority", "Location", "Latitude", "Longitude", "Why this point"],
        ["text", "text", "float2", "float2", "text"],
        rows,
    )
    manifest.save(paths.results / "manifests" / "weather.json")
    return manifest
