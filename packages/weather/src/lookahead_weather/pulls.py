"""Open-Meteo historical weather, one location per authority, pulled once and cached.

The archive API returns hourly ERA5 reanalysis values at a point. Each pull covers one
location and one calendar year and is cached as JSON under data/external/weather, so a
rerun never touches the network for a year it already has. The committed table is one
parquet file of every hour for every demand reporting authority, with the attribution
Open-Meteo asks for in its own file.

Open-Meteo's hourly timestamp marks the start of the hour; EIA's marks the end. The
parquet carries EIA's convention, so the row for hour ending 13:00 UTC holds the reading
Open-Meteo labels 12:00.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import polars as pl

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = ("temperature_2m", "relative_humidity_2m")
ATTRIBUTION = (
    "Weather data by Open-Meteo.com (https://open-meteo.com), licensed under CC BY 4.0 "
    "(https://creativecommons.org/licenses/by/4.0/), built on ERA5 reanalysis from the "
    "Copernicus Climate Change Service."
)
ARCHIVE_LAG_DAYS = 7


def year_ranges(first: date, last: date) -> list[tuple[int, date, date]]:
    """One (year, start, end) per calendar year between two dates, clipped at both ends."""
    out: list[tuple[int, date, date]] = []
    for year in range(first.year, last.year + 1):
        start = max(first, date(year, 1, 1))
        end = min(last, date(year, 12, 31))
        if start <= end:
            out.append((year, start, end))
    return out


def cache_path(cache: Path, authority: str, year: int) -> Path:
    return cache / f"{authority}_{year}.json"


def pull_year(
    latitude: float, longitude: float, start: date, end: date, client: httpx.Client
) -> dict[str, object]:
    params = {
        "latitude": f"{latitude:.4f}",
        "longitude": f"{longitude:.4f}",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": ",".join(VARIABLES),
        "timezone": "UTC",
    }
    for _attempt in range(6):
        response = client.get(ARCHIVE_URL, params=params, timeout=120.0)
        if response.status_code == 429:
            time.sleep(90.0)
            continue
        response.raise_for_status()
        payload: dict[str, object] = response.json()
        if "hourly" not in payload:
            raise ValueError(f"no hourly block for {latitude},{longitude} {start} to {end}")
        return payload
    raise RuntimeError(f"Open-Meteo kept answering 429 for {latitude},{longitude} {start}")


def ensure_cache(
    locations: pl.DataFrame, cache: Path, first: date, last: date, client: httpx.Client | None = None
) -> list[Path]:
    """Every (authority, year) JSON present, pulling the missing ones when a client is given."""
    cache.mkdir(parents=True, exist_ok=True)
    have: list[Path] = []
    missing: list[tuple[str, int, date, date, float, float]] = []
    for row in locations.iter_rows(named=True):
        for year, start, end in year_ranges(first, last):
            path = cache_path(cache, str(row["authority"]), year)
            if path.exists():
                have.append(path)
            else:
                missing.append(
                    (str(row["authority"]), year, start, end, float(row["latitude"]), float(row["longitude"]))
                )
    if missing and client is None:
        names = [f"{a}_{y}" for a, y, *_ in missing]
        raise FileNotFoundError(
            f"{len(missing)} weather pulls are missing from {cache} and this machine has no client for Open-Meteo: "
            + ", ".join(names[:8])
            + (" ..." if len(names) > 8 else "")
        )
    for authority, year, start, end, lat, lon in missing:
        assert client is not None
        payload = pull_year(lat, lon, start, end, client)
        path = cache_path(cache, authority, year)
        path.write_text(json.dumps(payload), encoding="utf-8")
        have.append(path)
        time.sleep(1.2)
    return sorted(have)


def frame_from_json(path: Path, authority: str) -> pl.DataFrame:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    hourly = payload["hourly"]
    starts = (
        pl.Series("start_utc", hourly["time"])
        .str.strptime(pl.Datetime("us"), "%Y-%m-%dT%H:%M")
        .dt.replace_time_zone("UTC")
    )
    # Open-Meteo stamps the start of the hour; the panel uses EIA's hour ending.
    ending = starts + timedelta(hours=1)
    return pl.DataFrame(
        {
            "authority": [authority] * len(ending),
            "utc_hour": ending,
            "temperature_c": pl.Series(hourly["temperature_2m"], dtype=pl.Float64),
            "humidity_pct": pl.Series(hourly["relative_humidity_2m"], dtype=pl.Float64),
        }
    )


def assemble(locations: pl.DataFrame, cache: Path, first: date, last: date) -> pl.DataFrame:
    """The committed hourly weather table from the cache, one row per authority and hour ending."""
    frames: list[pl.DataFrame] = []
    for row in locations.iter_rows(named=True):
        authority = str(row["authority"])
        for year, _, _ in year_ranges(first, last):
            path = cache_path(cache, authority, year)
            if not path.exists():
                raise FileNotFoundError(f"missing weather pull {path.name}")
            frames.append(frame_from_json(path, authority))
    weather = (
        pl.concat(frames)
        .unique(subset=["authority", "utc_hour"], keep="last")
        .sort(["authority", "utc_hour"])
    )
    return weather


def last_archived_day(today: date | None = None) -> date:
    today = today or datetime.now(UTC).date()
    return today - timedelta(days=ARCHIVE_LAG_DAYS)
