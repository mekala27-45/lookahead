"""The hierarchy table: the lower 48, the interconnections, the regions, the authorities and
the subregions, built from EIA's own region assignment and the subregion files.

Levels: 0 the lower 48, 1 the interconnection, 2 the region, 3 the balancing authority,
4 the subregion. A node's parent is the node one level up; a leaf is an authority without
subregions or a subregion. The summing matrix in packages/hierarchy is built from this
table and nothing else, and a test checks that its rows match it.
"""

from __future__ import annotations

import polars as pl
from lookahead_core.config import INTERCONNECTIONS, LOWER_48, REGION_LABELS

COLUMNS = ("node", "parent", "level", "kind", "label")


def build_hierarchy(regions: pl.DataFrame, subregions: pl.DataFrame | None) -> pl.DataFrame:
    """``regions`` has authority and region for every demand reporting authority;
    ``subregions`` has authority and subregion pairs (or None)."""
    if regions.height == 0:
        raise ValueError("the hierarchy needs at least one authority")
    region_to_interconnection = {r: ic for ic, rs in INTERCONNECTIONS.items() for r in rs}
    unknown = sorted(set(regions["region"].to_list()) - set(region_to_interconnection))
    if unknown:
        raise ValueError(f"regions without an interconnection assignment: {unknown}")
    rows: list[tuple[str, str | None, int, str, str]] = [(LOWER_48, None, 0, "lower48", "Lower 48 states")]
    for interconnection in INTERCONNECTIONS:
        rows.append((interconnection, LOWER_48, 1, "interconnection", f"{interconnection} Interconnection"))
    present_regions = sorted(set(regions["region"].to_list()))
    for region in present_regions:
        rows.append(
            (region, region_to_interconnection[region], 2, "region", REGION_LABELS.get(region, region))
        )
    for authority, region in sorted(
        zip(regions["authority"].to_list(), regions["region"].to_list(), strict=True)
    ):
        rows.append((authority, region, 3, "authority", authority))
    if subregions is not None and subregions.height:
        pairs = subregions.select("authority", "subregion").unique().sort(["authority", "subregion"])
        known = set(regions["authority"].to_list())
        for authority, subregion in pairs.iter_rows():
            if authority not in known:
                continue
            rows.append((f"{authority}.{subregion}", authority, 4, "subregion", f"{authority} {subregion}"))
    frame = pl.DataFrame(rows, schema=list(COLUMNS), orient="row")
    if frame["node"].n_unique() != frame.height:
        raise ValueError("hierarchy nodes are not unique")
    return frame


def leaves(hierarchy: pl.DataFrame) -> list[str]:
    parents = set(hierarchy["parent"].drop_nulls().to_list())
    return [n for n in hierarchy["node"].to_list() if n not in parents]


def children_of(hierarchy: pl.DataFrame, node: str) -> list[str]:
    return hierarchy.filter(pl.col("parent") == node)["node"].to_list()
