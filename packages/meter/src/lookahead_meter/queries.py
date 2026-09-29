"""DuckDB over the readings parquet: profiles, pre-period means, event consumption, cluster loads.

Every query runs against data/external/london/readings.parquet (household, tariff, ts, kwh),
which `make data` writes from the release and which is never committed. Household identifiers
never leave this module in a committed table: the outputs are cluster level, event level or
per household counts without the identifier.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl

READINGS = "readings"


def connect(readings: Path, threads: int = 2, memory: str = "3GB") -> duckdb.DuckDBPyConnection:
    if not readings.exists():
        raise FileNotFoundError(f"{readings} is missing; run `make data` to read the London release")
    con = duckdb.connect()
    con.execute(f"PRAGMA threads={threads}")
    con.execute(f"SET memory_limit='{memory}'")
    con.execute(f"SET temp_directory='{readings.parent / 'duckdb_tmp'}'")
    con.execute(f"create view {READINGS} as select * from read_parquet('{readings.as_posix()}')")
    return con


def profiles(con: duckdb.DuckDBPyConnection, start: str, end: str) -> pl.DataFrame:
    """Mean kWh per half hour slot by weekday or weekend per household over [start, end), with the
    household's mean and the days it reported."""
    frame = con.execute(
        f"""
        with base as (
          select household, tariff, ts, kwh from {READINGS}
          where ts >= timestamp '{start}' and ts < timestamp '{end}' and kwh is not null
        ),
        slots as (
          select household, tariff,
                 case when dayofweek(ts) in (0, 6) then 'weekend' else 'weekday' end as daytype,
                 cast(hour(ts) * 2 + minute(ts) / 30 as integer) as slot,
                 avg(kwh) as kwh, count(*) as n
          from base group by 1, 2, 3, 4
        ),
        totals as (
          select household, avg(kwh) as mean_kwh, count(distinct cast(ts as date)) as days
          from base group by 1
        )
        select s.household, s.tariff, s.daytype, s.slot, s.kwh, s.n, t.mean_kwh, t.days
        from slots s join totals t using (household)
        order by s.household, s.daytype, s.slot
        """
    ).pl()
    return frame


def pre_period_means(con: duckdb.DuckDBPyConnection, start: str, end: str) -> pl.DataFrame:
    return con.execute(
        f"""
        select household, tariff, avg(kwh) as pre_mean_kwh, count(*) as pre_readings
        from {READINGS}
        where ts >= timestamp '{start}' and ts < timestamp '{end}' and kwh is not null
        group by 1, 2 order by 1
        """
    ).pl()


def households_covering(
    con: duckdb.DuckDBPyConnection, start: str, end: str, min_share: float
) -> pl.DataFrame:
    """Households with at least the stated share of the half hours in [start, end)."""
    return con.execute(
        f"""
        with counts as (
          select household, tariff, count(*) as n
          from {READINGS}
          where ts >= timestamp '{start}' and ts < timestamp '{end}' and kwh is not null
          group by 1, 2
        )
        select household, tariff, n from counts
        where n >= {min_share} * date_diff('minute', timestamp '{start}', timestamp '{end}') / 30
        order by household
        """
    ).pl()


def slot_consumption(
    con: duckdb.DuckDBPyConnection, households: pl.DataFrame, slots: pl.DataFrame
) -> pl.DataFrame:
    """Mean kWh per household over the half hours of each (event_id, role) group in ``slots``
    (columns event_id, role, ts, day); returns household, event_id, role, kwh, n, days."""
    con.register("wanted_households", households.select("household").to_arrow())
    con.register("wanted_slots", slots.to_arrow())
    frame = con.execute(
        f"""
        select r.household, s.event_id, s.role, avg(r.kwh) as kwh, count(*) as n,
               count(distinct s.day) as days
        from {READINGS} r
        join wanted_households h on r.household = h.household
        join wanted_slots s on r.ts = s.ts
        where r.kwh is not null
        group by 1, 2, 3
        """
    ).pl()
    con.unregister("wanted_households")
    con.unregister("wanted_slots")
    return frame


def hourly_cluster_loads(
    con: duckdb.DuckDBPyConnection, assignment: pl.DataFrame, start: str, end: str
) -> pl.DataFrame:
    """Hourly kWh per cluster over [start, end) for the households in ``assignment`` (household,
    cluster), with the count of households reporting in the hour."""
    con.register("panel_households", assignment.select("household", "cluster").to_arrow())
    frame = con.execute(
        f"""
        select p.cluster, date_trunc('hour', r.ts) as ts, sum(r.kwh) as kwh,
               count(distinct r.household) as households
        from {READINGS} r join panel_households p on r.household = p.household
        where r.ts >= timestamp '{start}' and r.ts < timestamp '{end}' and r.kwh is not null
        group by 1, 2 order by 1, 2
        """
    ).pl()
    con.unregister("panel_households")
    return frame
