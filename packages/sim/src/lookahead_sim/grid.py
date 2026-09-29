"""A synthetic grid with known truth.

Two regions, eight authorities, four subregions under two of them, three years of hourly
demand. Each authority has a baseline with daily, weekly and yearly shape and a stated
growth, a V shaped response to its region's temperature with known heating and cooling
thresholds and slopes, holiday effects of known size, autocorrelated noise at a stated
level, planted events in a truth table (a load shed, a meter that reports zero, a
duplicated hour, two skipped hours), and a synthetic operator forecast with a known error
structure. Everything the harness later measures on it is known here first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl
from lookahead_core.model import StrictModel
from lookahead_core.seeds import rng

HOURS_PER_YEAR = 8760


class AuthoritySpec(StrictModel):
    name: str
    region: str
    base_mw: float
    daily_amplitude: float
    weekend_factor: float
    yearly_amplitude: float
    growth_per_year: float
    heating_threshold_c: float
    cooling_threshold_c: float
    heating_slope_mw_per_c: float
    cooling_slope_mw_per_c: float
    holiday_effect: float
    """Multiplicative effect on a holiday, for example -0.08 for eight percent less demand."""
    temperature_offset_c: float
    subregions: tuple[tuple[str, float], ...] = ()
    """Subregion names and their shares of the authority; shares sum below one, the gap is stated."""
    utc_offset_hours: int = -6


class GridSpec(StrictModel):
    start: date = date(2023, 1, 1)
    years: int = 3
    noise_sigma: float = 0.01
    """Standard deviation of the multiplicative AR(1) noise, as a share of the baseline."""
    noise_phi: float = 0.8
    temperature_sensitivity: float = 1.0
    """Multiplies every heating and cooling slope; the recovery study varies it."""
    missing_rate: float = 0.0
    """Share of hours whose observed demand is dropped at random."""
    operator_error_sigma: float = 0.03
    """The synthetic operator's multiplicative AR(1) error, as a share of the truth."""
    operator_error_phi: float = 0.6
    operator_bias: float = 0.005
    subregion_gap: float = 0.02
    """The subregion total sits this share below the authority, as in the real source."""
    authorities: tuple[AuthoritySpec, ...] = ()


def default_authorities() -> tuple[AuthoritySpec, ...]:
    north = "North"
    south = "South"
    return (
        AuthoritySpec(
            name="NA1",
            region=north,
            base_mw=12_000,
            daily_amplitude=0.18,
            weekend_factor=0.92,
            yearly_amplitude=0.06,
            growth_per_year=0.01,
            heating_threshold_c=14.0,
            cooling_threshold_c=20.0,
            heating_slope_mw_per_c=260.0,
            cooling_slope_mw_per_c=420.0,
            holiday_effect=-0.08,
            temperature_offset_c=0.0,
            subregions=(("E", 0.55), ("W", 0.43)),
            utc_offset_hours=-5,
        ),
        AuthoritySpec(
            name="NA2",
            region=north,
            base_mw=4_500,
            daily_amplitude=0.15,
            weekend_factor=0.94,
            yearly_amplitude=0.05,
            growth_per_year=0.005,
            heating_threshold_c=12.0,
            cooling_threshold_c=22.0,
            heating_slope_mw_per_c=120.0,
            cooling_slope_mw_per_c=110.0,
            holiday_effect=-0.06,
            temperature_offset_c=-2.0,
            utc_offset_hours=-5,
        ),
        AuthoritySpec(
            name="NA3",
            region=north,
            base_mw=800,
            daily_amplitude=0.20,
            weekend_factor=0.90,
            yearly_amplitude=0.08,
            growth_per_year=0.0,
            heating_threshold_c=16.0,
            cooling_threshold_c=18.0,
            heating_slope_mw_per_c=30.0,
            cooling_slope_mw_per_c=20.0,
            holiday_effect=-0.10,
            temperature_offset_c=1.0,
            utc_offset_hours=-6,
        ),
        AuthoritySpec(
            name="NA4",
            region=north,
            base_mw=2_200,
            daily_amplitude=0.12,
            weekend_factor=0.96,
            yearly_amplitude=0.04,
            growth_per_year=0.02,
            heating_threshold_c=10.0,
            cooling_threshold_c=24.0,
            heating_slope_mw_per_c=70.0,
            cooling_slope_mw_per_c=60.0,
            holiday_effect=-0.05,
            temperature_offset_c=-1.0,
            utc_offset_hours=-6,
        ),
        AuthoritySpec(
            name="SA1",
            region=south,
            base_mw=30_000,
            daily_amplitude=0.22,
            weekend_factor=0.93,
            yearly_amplitude=0.10,
            growth_per_year=0.015,
            heating_threshold_c=12.0,
            cooling_threshold_c=18.0,
            heating_slope_mw_per_c=400.0,
            cooling_slope_mw_per_c=1_500.0,
            holiday_effect=-0.07,
            temperature_offset_c=0.0,
            subregions=(("C", 0.60), ("H", 0.38)),
            utc_offset_hours=-6,
        ),
        AuthoritySpec(
            name="SA2",
            region=south,
            base_mw=6_000,
            daily_amplitude=0.25,
            weekend_factor=0.95,
            yearly_amplitude=0.12,
            growth_per_year=0.01,
            heating_threshold_c=10.0,
            cooling_threshold_c=20.0,
            heating_slope_mw_per_c=90.0,
            cooling_slope_mw_per_c=300.0,
            holiday_effect=-0.06,
            temperature_offset_c=2.0,
            utc_offset_hours=-6,
        ),
        AuthoritySpec(
            name="SA3",
            region=south,
            base_mw=300,
            daily_amplitude=0.30,
            weekend_factor=0.97,
            yearly_amplitude=0.15,
            growth_per_year=0.03,
            heating_threshold_c=14.0,
            cooling_threshold_c=22.0,
            heating_slope_mw_per_c=4.0,
            cooling_slope_mw_per_c=18.0,
            holiday_effect=-0.04,
            temperature_offset_c=3.0,
            utc_offset_hours=-5,
        ),
        AuthoritySpec(
            name="SA4",
            region=south,
            base_mw=1_400,
            daily_amplitude=0.20,
            weekend_factor=0.91,
            yearly_amplitude=0.09,
            growth_per_year=0.0,
            heating_threshold_c=8.0,
            cooling_threshold_c=24.0,
            heating_slope_mw_per_c=20.0,
            cooling_slope_mw_per_c=70.0,
            holiday_effect=-0.09,
            temperature_offset_c=-1.0,
            utc_offset_hours=-7,
        ),
    )


class PlantedEvent(StrictModel):
    kind: str
    """load_shed, meter_zero, duplicate_hour or skipped_hours."""
    authority: str
    start_hour: int
    """Position in the hourly series."""
    duration_hours: int
    size_share: float = 0.0
    """For a load shed, the share of demand removed."""


@dataclass(frozen=True)
class Grid:
    spec: GridSpec
    panel: pl.DataFrame
    """authority, utc_hour, utc_offset_hours, demand (observed, with the planted defects), demand_true,
    forecast_operator, temperature_c, humidity_pct, region, plus the event flags."""
    subregions: pl.DataFrame
    events: tuple[PlantedEvent, ...]
    hierarchy: pl.DataFrame
    truth: dict[str, dict[str, float]]

    @property
    def hours(self) -> int:
        return self.spec.years * HOURS_PER_YEAR


def _holiday_flags(start: datetime, hours: int, offset: int) -> np.ndarray:
    from lookahead_features.build import is_holiday

    flags = np.zeros(hours, dtype=bool)
    cache: dict[date, bool] = {}
    for i in range(hours):
        day = (start + timedelta(hours=i + offset - 1)).date()
        if day not in cache:
            cache[day] = is_holiday(day, "US")
        flags[i] = cache[day]
    return flags


def _ar1(generator: np.random.Generator, n: int, sigma: float, phi: float) -> np.ndarray:
    innovations = generator.normal(0.0, sigma * math.sqrt(1 - phi**2), n)
    out = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc = phi * acc + innovations[i]
        out[i] = acc
    return out


def region_temperature(generator: np.random.Generator, hours: int, region: str) -> np.ndarray:
    """A seasonal, diurnal temperature path with autocorrelated weather; warmer in the south."""
    t = np.arange(hours)
    mean = 12.0 if region == "North" else 20.0
    seasonal = -11.0 * np.cos(2 * np.pi * (t / 24 - 15) / 365.25)
    diurnal = 5.0 * np.sin(2 * np.pi * (t - 9) / 24)
    weather = 4.0 * _ar1(generator, hours, 1.0, 0.985)
    return mean + seasonal + diurnal + weather


def simulate(spec: GridSpec, seed: int) -> Grid:
    authorities = spec.authorities or default_authorities()
    hours = spec.years * HOURS_PER_YEAR
    start = datetime(spec.start.year, spec.start.month, spec.start.day, 1, tzinfo=UTC)
    stamps = pl.datetime_range(
        start, start + timedelta(hours=hours - 1), interval="1h", time_zone="UTC", eager=True
    )
    t = np.arange(hours)
    temps = {
        region: region_temperature(rng(seed, "temperature", region), hours, region)
        for region in ("North", "South")
    }
    frames: list[pl.DataFrame] = []
    sub_frames: list[pl.DataFrame] = []
    truth: dict[str, dict[str, float]] = {}
    events: list[PlantedEvent] = []
    for a in authorities:
        g = rng(seed, "authority", a.name)
        temperature = temps[a.region] + a.temperature_offset_c
        humidity = np.clip(65 + 15 * np.sin(2 * np.pi * (t - 3) / 24) + 8 * _ar1(g, hours, 1.0, 0.95), 5, 100)
        local_hour = ((t + a.utc_offset_hours) % 24).astype(float)
        weekday = (np.floor((t + a.utc_offset_hours - 1) / 24).astype(int) + spec.start.weekday()) % 7
        daily = (
            1.0
            + a.daily_amplitude * np.sin(2 * np.pi * (local_hour - 9) / 24)
            + 0.4 * a.daily_amplitude * np.sin(4 * np.pi * (local_hour - 6) / 24)
        )
        weekly = np.where(weekday >= 5, a.weekend_factor, 1.0)
        yearly = 1.0 + a.yearly_amplitude * np.cos(2 * np.pi * (t / 24 - 200) / 365.25)
        growth = (1.0 + a.growth_per_year) ** (t / HOURS_PER_YEAR)
        holidays = _holiday_flags(start, hours, a.utc_offset_hours)
        baseline = a.base_mw * daily * weekly * yearly * growth * (1.0 + a.holiday_effect * holidays)
        heating = (
            np.maximum(a.heating_threshold_c - temperature, 0.0)
            * a.heating_slope_mw_per_c
            * spec.temperature_sensitivity
        )
        cooling = (
            np.maximum(temperature - a.cooling_threshold_c, 0.0)
            * a.cooling_slope_mw_per_c
            * spec.temperature_sensitivity
        )
        # Cooling bites in the afternoon and evening; heating in the morning and night.
        evening = 1.0 + 0.5 * np.sin(2 * np.pi * (local_hour - 12) / 24)
        night = 1.0 + 0.3 * np.cos(2 * np.pi * (local_hour - 3) / 24)
        noise = _ar1(g, hours, spec.noise_sigma, spec.noise_phi)
        demand_true = (baseline + heating * night + cooling * evening) * (1.0 + noise)
        operator_error = (
            _ar1(g, hours, spec.operator_error_sigma, spec.operator_error_phi) + spec.operator_bias
        )
        forecast_operator = demand_true * (1.0 + operator_error)
        observed = demand_true.copy()
        flags = {
            k: np.zeros(hours, dtype=bool)
            for k in ("load_shed", "meter_zero", "duplicate_hour", "skipped_hours")
        }
        # Planted events in the last year, at stated positions, one of each kind across the grid.
        last_year_start = hours - HOURS_PER_YEAR
        planted = _plant(a.name, authorities, last_year_start, g)
        for event in planted:
            s, e = event.start_hour, event.start_hour + event.duration_hours
            if event.kind == "load_shed":
                observed[s:e] = demand_true[s:e] * (1.0 - event.size_share)
                flags["load_shed"][s:e] = True
            elif event.kind == "meter_zero":
                observed[s:e] = 0.0
                flags["meter_zero"][s:e] = True
            elif event.kind == "duplicate_hour":
                flags["duplicate_hour"][s:e] = True
            elif event.kind == "skipped_hours":
                observed[s:e] = np.nan
                flags["skipped_hours"][s:e] = True
        events.extend(planted)
        if spec.missing_rate > 0:
            drop = g.random(hours) < spec.missing_rate
            observed[drop] = np.nan
        frame = pl.DataFrame(
            {
                "authority": [a.name] * hours,
                "utc_hour": stamps,
                "utc_offset_hours": np.full(hours, a.utc_offset_hours, dtype=np.int8),
                "demand": observed,
                "demand_true": demand_true,
                "forecast_operator": forecast_operator,
                "temperature_c": temperature,
                "humidity_pct": humidity,
                "region": [a.region] * hours,
                **{k: v for k, v in flags.items()},
            }
        )
        frames.append(frame)
        for sub, share in a.subregions:
            sub_frames.append(
                pl.DataFrame(
                    {
                        "authority": [a.name] * hours,
                        "subregion": [sub] * hours,
                        "utc_hour": stamps,
                        "demand": demand_true
                        * share
                        * (1.0 - spec.subregion_gap)
                        / max(sum(s for _, s in a.subregions), 1e-9)
                        * sum(s for _, s in a.subregions),
                    }
                )
            )
        truth[a.name] = {
            "heating_threshold_c": a.heating_threshold_c,
            "cooling_threshold_c": a.cooling_threshold_c,
            "heating_slope_mw_per_c": a.heating_slope_mw_per_c * spec.temperature_sensitivity,
            "cooling_slope_mw_per_c": a.cooling_slope_mw_per_c * spec.temperature_sensitivity,
            "holiday_effect": a.holiday_effect,
            "operator_mape_expected": _expected_operator_mape(spec),
            "base_mw": a.base_mw,
        }
    panel = pl.concat(frames)
    subregions = (
        pl.concat(sub_frames)
        if sub_frames
        else pl.DataFrame(
            schema={
                "authority": pl.Utf8,
                "subregion": pl.Utf8,
                "utc_hour": pl.Datetime("us", "UTC"),
                "demand": pl.Float64,
            }
        )
    )
    hierarchy = _hierarchy(authorities)
    return Grid(
        spec=spec, panel=panel, subregions=subregions, events=tuple(events), hierarchy=hierarchy, truth=truth
    )


def _plant(
    name: str, authorities: tuple[AuthoritySpec, ...], last_year_start: int, g: np.random.Generator
) -> list[PlantedEvent]:
    """One planted event per authority in the last year, the kind rotating through the four."""
    index = [a.name for a in authorities].index(name)
    kinds = ("load_shed", "meter_zero", "duplicate_hour", "skipped_hours")
    kind = kinds[index % 4]
    # Events sit in the test year at stated day offsets so every condition and seed plants them
    # at the same place; the size varies by seed within a stated range.
    day = 40 + 35 * index
    start = last_year_start + day * 24 + 17
    if kind == "load_shed":
        return [
            PlantedEvent(
                kind=kind,
                authority=name,
                start_hour=start,
                duration_hours=int(g.integers(6, 18)),
                size_share=float(g.uniform(0.12, 0.30)),
            )
        ]
    if kind == "meter_zero":
        return [
            PlantedEvent(kind=kind, authority=name, start_hour=start, duration_hours=int(g.integers(3, 9)))
        ]
    if kind == "duplicate_hour":
        return [PlantedEvent(kind=kind, authority=name, start_hour=start, duration_hours=1)]
    return [PlantedEvent(kind=kind, authority=name, start_hour=start, duration_hours=2)]


def _expected_operator_mape(spec: GridSpec) -> float:
    """E|e| for e ~ N(bias, sigma) in the stationary AR(1): sigma sqrt(2/pi) when the bias is small."""
    sigma = spec.operator_error_sigma
    b = spec.operator_bias
    # Mean absolute value of a normal with mean b and standard deviation sigma.
    return sigma * math.sqrt(2 / math.pi) * math.exp(-(b**2) / (2 * sigma**2)) + b * math.erf(
        b / (sigma * math.sqrt(2))
    )


def _hierarchy(authorities: tuple[AuthoritySpec, ...]) -> pl.DataFrame:
    rows: list[tuple[str, str | None, int, str, str]] = [("GRID", None, 0, "lower48", "Synthetic grid")]
    rows.append(("Synthetic", "GRID", 1, "interconnection", "Synthetic interconnection"))
    for region in ("North", "South"):
        rows.append((region, "Synthetic", 2, "region", region))
    for a in authorities:
        rows.append((a.name, a.region, 3, "authority", a.name))
    for a in authorities:
        for sub, _ in a.subregions:
            rows.append((f"{a.name}.{sub}", a.name, 4, "subregion", f"{a.name} {sub}"))
    return pl.DataFrame(rows, schema=["node", "parent", "level", "kind", "label"], orient="row")


def events_frame(grid: Grid) -> pl.DataFrame:
    rows = []
    for e in grid.events:
        start = grid.panel["utc_hour"][0] + timedelta(hours=e.start_hour)
        rows.append([e.kind, e.authority, e.start_hour, start, e.duration_hours, e.size_share])
    return pl.DataFrame(
        rows,
        schema=["kind", "authority", "start_position", "start_utc", "duration_hours", "size_share"],
        orient="row",
    )


def raw_observations(grid: Grid) -> pl.DataFrame:
    """The grid as a feed would deliver it: the duplicated hour appears twice, the skipped hours
    are absent, the meter outage reports zero, and the quarantine rules have not run yet."""
    panel = grid.panel
    duplicated = panel.filter(pl.col("duplicate_hour"))
    without_skips = panel.filter(~pl.col("skipped_hours"))
    raw = pl.concat([without_skips, duplicated]).sort(["authority", "utc_hour"])
    return raw.with_columns(
        pl.lit("simulator").alias("source_file"),
        pl.col("demand_true").alias("net_generation"),
        pl.lit(0.0).alias("interchange"),
    )
