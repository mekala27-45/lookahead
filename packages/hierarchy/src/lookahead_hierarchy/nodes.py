"""Every node of the hierarchy as a series, so each can be forecast directly.

Authorities come from the panel. Subregions come from the subregion table where they cover
the validation and test windows. Because the source's subregion totals do not equal their
authority (the gap is measured and published), each authority with subregions gets a
remainder node, authority minus the subregion total, so the actuals add up to the megawatt
at every level and reconciliation has an exact target. Regions, interconnections and the
lower 48 are sums of their authorities, null in any hour where a member is missing; their
weather is the load weighted mean of their members' and their operator forecast is the sum
of their members' published forecasts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl

REMAINDER = "rest"


def _window_coverage(frame: pl.DataFrame, key: str, start: datetime, end: datetime) -> pl.DataFrame:
    hour_after = pl.col("utc_hour") - pl.duration(hours=1)
    hours = float((end - start).total_seconds() // 3600)
    return (
        frame.filter((hour_after >= start) & (hour_after < end))
        .group_by(key)
        .agg((pl.col("demand").is_not_null() & pl.col("demand").is_not_nan()).sum().alias("with_demand"))
        .with_columns((pl.col("with_demand") / hours).alias("coverage"))
    )


def eligible_subregions(
    subregions: pl.DataFrame, authorities: list[str], windows: dict[str, str | int], minimum: float = 0.9
) -> pl.DataFrame:
    """Subregion rows (authority, subregion) of the given authorities that cover the validation and test windows."""
    validation_start = datetime.fromisoformat(str(windows["validation_start"])).replace(tzinfo=UTC)
    test_end = datetime.fromisoformat(str(windows["test_end"])).replace(tzinfo=UTC) + timedelta(days=1)
    frame = subregions.filter(pl.col("authority").is_in(authorities)).with_columns(
        (pl.col("authority") + "." + pl.col("subregion")).alias("node")
    )
    coverage = _window_coverage(frame, "node", validation_start, test_end)
    keep = coverage.filter(pl.col("coverage") >= minimum)["node"].to_list()
    return (
        frame.filter(pl.col("node").is_in(keep))
        .select("authority", "subregion", "node")
        .unique()
        .sort("node")
    )


def node_table(hierarchy: pl.DataFrame, authorities: list[str], eligible: pl.DataFrame) -> pl.DataFrame:
    """The reconciliation hierarchy: the levels above, the given authorities, their eligible
    subregions, and a remainder node per authority that has any."""
    base = hierarchy.filter(pl.col("level") <= 2)
    auth_rows = hierarchy.filter((pl.col("level") == 3) & pl.col("node").is_in(authorities))
    regions_present = set(auth_rows["parent"].to_list())
    regions = base.filter((pl.col("level") == 2) & pl.col("node").is_in(list(regions_present)))
    interconnections_present = set(regions["parent"].to_list())
    interconnections = base.filter(
        (pl.col("level") == 1) & pl.col("node").is_in(list(interconnections_present))
    )
    top = base.filter(pl.col("level") == 0)
    sub_rows = [
        {
            "node": r["node"],
            "parent": r["authority"],
            "level": 4,
            "kind": "subregion",
            "label": f"{r['authority']} {r['subregion']}",
        }
        for r in eligible.iter_rows(named=True)
    ]
    with_subs = sorted(set(eligible["authority"].to_list()))
    rest_rows = [
        {"node": f"{a}.{REMAINDER}", "parent": a, "level": 4, "kind": "remainder", "label": f"{a} remainder"}
        for a in with_subs
    ]
    extra = pl.DataFrame(
        sub_rows + rest_rows,
        schema={"node": pl.Utf8, "parent": pl.Utf8, "level": pl.Int64, "kind": pl.Utf8, "label": pl.Utf8},
    )
    frame = pl.concat([top, interconnections, regions, auth_rows, extra], how="vertical_relaxed")
    return frame.with_columns(pl.col("level").cast(pl.Int64)).sort(["level", "node"])


def build_node_panel(
    panel: pl.DataFrame,
    subregions: pl.DataFrame,
    weather: pl.DataFrame | None,
    nodes: pl.DataFrame,
    authorities: list[str],
) -> pl.DataFrame:
    """One row per node and hour with demand, forecast_operator, utc_offset_hours, temperature_c,
    humidity_pct and region, in the panel's schema, so the backends read it unchanged."""
    auth = panel.filter(pl.col("authority").is_in(authorities)).select(
        "authority", "utc_hour", "utc_offset_hours", "demand", "forecast_operator", "region"
    )
    if weather is not None:
        auth = auth.join(
            weather.select("authority", "utc_hour", "temperature_c", "humidity_pct"),
            on=["authority", "utc_hour"],
            how="left",
        )
    elif "temperature_c" in panel.columns:
        auth = auth.join(
            panel.select("authority", "utc_hour", "temperature_c", "humidity_pct"),
            on=["authority", "utc_hour"],
            how="left",
        )
    else:
        auth = auth.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("temperature_c"),
            pl.lit(None, dtype=pl.Float64).alias("humidity_pct"),
        )
    auth = auth.with_columns(pl.col("demand").cast(pl.Float64), pl.col("forecast_operator").cast(pl.Float64))
    typical = auth.group_by("authority").agg(pl.col("demand").mean().alias("weight"))
    auth = auth.join(typical, on="authority", how="left")
    columns = [
        "node",
        "utc_hour",
        "utc_offset_hours",
        "demand",
        "forecast_operator",
        "region",
        "temperature_c",
        "humidity_pct",
    ]
    frames: list[pl.DataFrame] = [
        auth.drop("weight").with_columns(pl.col("authority").alias("node")).drop("authority").select(columns)
    ]

    # Aggregates: sums over members, null when any member is null; weather load weighted.
    parents = dict(zip(nodes["node"].to_list(), nodes["parent"].to_list(), strict=True))
    level = dict(zip(nodes["node"].to_list(), nodes["level"].to_list(), strict=True))

    def members(node: str) -> list[str]:
        return [a for a in authorities if _ancestor_of(a, node, parents)]

    for node in nodes.filter(pl.col("level") <= 2)["node"].to_list():
        group = members(node)
        if not group:
            continue
        sub = auth.filter(pl.col("authority").is_in(group))
        agg = (
            sub.group_by("utc_hour")
            .agg(
                pl.len().alias("members"),
                pl.col("demand").is_null().sum().alias("missing_members"),
                pl.col("demand").sum().alias("demand"),
                pl.col("forecast_operator").is_null().sum().alias("missing_operator"),
                pl.col("forecast_operator").sum().alias("forecast_operator"),
                (
                    (pl.col("temperature_c") * pl.col("weight")).sum()
                    / pl.col("weight").filter(pl.col("temperature_c").is_not_null()).sum()
                ).alias("temperature_c"),
                (
                    (pl.col("humidity_pct") * pl.col("weight")).sum()
                    / pl.col("weight").filter(pl.col("humidity_pct").is_not_null()).sum()
                ).alias("humidity_pct"),
                pl.col("utc_offset_hours")
                .sort_by("weight", descending=True)
                .first()
                .alias("utc_offset_hours"),
            )
            .with_columns(
                pl.when(pl.col("missing_members") > 0).then(None).otherwise(pl.col("demand")).alias("demand"),
                pl.when(pl.col("missing_operator") > 0)
                .then(None)
                .otherwise(pl.col("forecast_operator"))
                .alias("forecast_operator"),
                pl.lit(node).alias("node"),
                pl.lit(node if level[node] == 2 else "aggregate").alias("region"),
            )
            # The aggregate covers only the hours where every member has a row.
            .filter(pl.col("members") == len(group))
            .select(
                "node",
                "utc_hour",
                "utc_offset_hours",
                "demand",
                "forecast_operator",
                "region",
                "temperature_c",
                "humidity_pct",
            )
        )
        frames.append(agg)

    # Subregions and remainders, with the parent's weather and offset.
    sub_nodes = nodes.filter(pl.col("level") == 4)
    if sub_nodes.height:
        subs = subregions.with_columns(
            (pl.col("authority") + "." + pl.col("subregion")).alias("node"), pl.col("demand").cast(pl.Float64)
        )
        parent_rows = auth.select(
            "authority",
            "utc_hour",
            "utc_offset_hours",
            "region",
            "temperature_c",
            "humidity_pct",
            pl.col("demand").alias("parent_demand"),
        )
        for authority in sorted(set(sub_nodes["parent"].to_list())):
            names = sub_nodes.filter((pl.col("parent") == authority) & (pl.col("kind") == "subregion"))[
                "node"
            ].to_list()
            part = subs.filter(pl.col("node").is_in(names)).select("node", "utc_hour", "demand")
            wide = part.join(parent_rows.filter(pl.col("authority") == authority), on="utc_hour", how="inner")
            frames.append(
                wide.with_columns(pl.lit(None, dtype=pl.Float64).alias("forecast_operator")).select(
                    "node",
                    "utc_hour",
                    "utc_offset_hours",
                    "demand",
                    "forecast_operator",
                    "region",
                    "temperature_c",
                    "humidity_pct",
                )
            )
            totals = (
                part.group_by("utc_hour")
                .agg(
                    pl.len().alias("parts"),
                    pl.col("demand").is_null().sum().alias("missing_parts"),
                    pl.col("demand").sum().alias("sub_total"),
                )
                .filter((pl.col("parts") == len(names)) & (pl.col("missing_parts") == 0))
            )
            rest = parent_rows.filter(pl.col("authority") == authority).join(
                totals, on="utc_hour", how="inner"
            )
            frames.append(
                rest.with_columns(
                    (pl.col("parent_demand") - pl.col("sub_total")).alias("demand"),
                    pl.lit(f"{authority}.{REMAINDER}").alias("node"),
                    pl.lit(None, dtype=pl.Float64).alias("forecast_operator"),
                ).select(
                    "node",
                    "utc_hour",
                    "utc_offset_hours",
                    "demand",
                    "forecast_operator",
                    "region",
                    "temperature_c",
                    "humidity_pct",
                )
            )
    out = pl.concat([f.select(columns) for f in frames], how="vertical_relaxed").rename({"node": "authority"})
    return _complete_hours(out).sort(["authority", "utc_hour"])


def _ancestor_of(authority: str, node: str, parents: dict[str, str | None]) -> bool:
    current: str | None = authority
    while current is not None:
        if current == node:
            return True
        current = parents.get(current)
    return False


def _complete_hours(frame: pl.DataFrame) -> pl.DataFrame:
    """Every node on a complete hourly grid from its first to its last hour, missing hours null."""
    spans = frame.group_by("authority").agg(
        pl.col("utc_hour").min().alias("start"), pl.col("utc_hour").max().alias("end")
    )
    grids = []
    for row in spans.iter_rows(named=True):
        hours = pl.datetime_range(row["start"], row["end"], interval="1h", time_zone="UTC", eager=True)
        grids.append(pl.DataFrame({"authority": [row["authority"]] * len(hours), "utc_hour": hours}))
    grid = pl.concat(grids)
    return grid.join(frame, on=["authority", "utc_hour"], how="left").with_columns(
        pl.col("utc_offset_hours")
        .fill_null(strategy="forward")
        .fill_null(strategy="backward")
        .over("authority"),
        pl.col("region").fill_null(strategy="forward").fill_null(strategy="backward").over("authority"),
    )


def actual_matrix(node_panel: pl.DataFrame, nodes: list[str], hours: pl.Series) -> np.ndarray:
    """Actual demand as hours by nodes, NaN where missing."""
    base = pl.DataFrame({"utc_hour": hours})
    columns = []
    for node in nodes:
        sub = node_panel.filter(pl.col("authority") == node).select("utc_hour", "demand")
        columns.append(
            base.join(sub, on="utc_hour", how="left")["demand"]
            .cast(pl.Float64)
            .fill_null(float("nan"))
            .to_numpy()
        )
    return np.stack(columns, axis=1)
