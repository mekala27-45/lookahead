"""The time of use analysis, exactly as the pre-registered plan says.

The dynamic tariff group was recruited, not randomized, so this is an observational comparison:
each dToU household is matched to a standard tariff household in the same load shape cluster
with the nearest pre-period mean, and every high price event of the 2013 schedule is graded by
difference in differences against the same half hours on comparison days. Intervals come from
a block bootstrap over events in calendar order, and Benjamini-Hochberg runs across the four
event types. The rebound is the same estimator on the hours after each event.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import polars as pl
from lookahead_core.seeds import rng
from lookahead_evaluation.bootstrap import benjamini_hochberg

from lookahead_meter.plan import PLAN, Plan

HALF_HOUR = timedelta(minutes=30)


@dataclass(frozen=True)
class HighPriceEvent:
    event_id: int
    start: datetime
    end: datetime
    """The last half hour of the event, inclusive."""
    half_hours: int
    event_type: str
    daytype: str


def high_price_events(tariff: pl.DataFrame, plan: Plan = PLAN) -> list[HighPriceEvent]:
    """Maximal runs of consecutive High half hours in the schedule."""
    if tariff.height == 0:
        raise ValueError("the tariff schedule is empty")
    runs = (
        tariff.sort("ts")
        .with_columns((pl.col("band") != pl.col("band").shift(1)).fill_null(True).cum_sum().alias("run"))
        .filter(pl.col("band") == "High")
        .group_by("run")
        .agg(pl.col("ts").min().alias("start"), pl.col("ts").max().alias("end"), pl.len().alias("half_hours"))
        .sort("start")
    )
    events = []
    for i, row in enumerate(runs.iter_rows(named=True)):
        start: datetime = row["start"]
        events.append(
            HighPriceEvent(
                event_id=i,
                start=start,
                end=row["end"],
                half_hours=int(row["half_hours"]),
                event_type=plan.event_type(start.hour),
                daytype="weekend" if start.weekday() >= 5 else "weekday",
            )
        )
    return events


def match_households(treated: pl.DataFrame, pool: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """One standard household per dToU household, same cluster, nearest pre-period mean, without
    replacement, on identifiers sorted; returns pairs (treated, control, cluster) and the number
    of dToU households dropped for want of a candidate."""
    if "cluster" not in treated.columns or "cluster" not in pool.columns:
        raise ValueError("matching needs a cluster column on both sides")
    if (pool["tariff"] != "Std").any() or (treated["tariff"] != "ToU").any():
        raise ValueError("the treated side has to be ToU and the pool Std")
    pairs: list[tuple[str, str, int]] = []
    dropped = 0
    for cluster in sorted(treated["cluster"].unique().to_list()):
        t = treated.filter(pl.col("cluster") == cluster).sort("household")
        candidates = pool.filter(pl.col("cluster") == cluster).sort("household")
        available = dict(
            zip(candidates["household"].to_list(), candidates["pre_mean_kwh"].to_list(), strict=True)
        )
        for household, mean in zip(t["household"].to_list(), t["pre_mean_kwh"].to_list(), strict=True):
            if not available:
                dropped += 1
                continue
            best = min(sorted(available), key=lambda h: (abs(available[h] - mean), h))
            pairs.append((household, best, int(cluster)))
            del available[best]
    frame = pl.DataFrame(pairs, schema=["treated", "control", "cluster"], orient="row")
    return frame, dropped


def slot_table(events: list[HighPriceEvent], tariff: pl.DataFrame, plan: Plan = PLAN) -> pl.DataFrame:
    """Every half hour the analysis reads, labelled (event_id, role, ts, day): the event's own half
    hours, the comparison days' same half hours, and the rebound half hours after the event with
    their comparison counterparts."""
    high = set(tariff.filter(pl.col("band") == "High")["ts"].to_list())
    rows: list[tuple[int, str, datetime, datetime]] = []
    for e in events:
        event_slots = [e.start + HALF_HOUR * i for i in range(e.half_hours)]
        rebound_slots = [e.end + HALF_HOUR * (i + 1) for i in range(plan.rebound_hours * 2)]
        for role, slots in (("event", event_slots), ("rebound", rebound_slots)):
            day0 = e.start.replace(hour=0, minute=0, second=0, microsecond=0)
            for ts in slots:
                rows.append((e.event_id, role, ts, day0))
            for offset in range(-plan.comparison_days_either_side, plan.comparison_days_either_side + 1):
                if offset == 0:
                    continue
                day = day0 + timedelta(days=offset)
                if (day.weekday() >= 5) != (e.daytype == "weekend"):
                    continue
                shifted = [ts + timedelta(days=offset) for ts in slots]
                if any(ts in high for ts in shifted):
                    continue
                for ts in shifted:
                    rows.append((e.event_id, f"{role}_comparison", ts, day))
    return pl.DataFrame(rows, schema=["event_id", "role", "ts", "day"], orient="row")


@dataclass
class TouResult:
    events: int
    treated: int
    pairs: int
    dropped: int
    per_event: pl.DataFrame
    """event_id, event_type, half_hours, start, did_kwh, control_event_kwh, response_pct, rebound_kwh, rebound_pct, pairs."""
    overall_kwh: float
    overall_kwh_lower: float
    overall_kwh_upper: float
    overall_pct: float
    overall_pct_lower: float
    overall_pct_upper: float
    rebound_pct: float
    rebound_pct_lower: float
    rebound_pct_upper: float
    by_type: pl.DataFrame
    """event_type, events, response_pct, lower, upper, p_value, rejected."""
    plan_hash: str = ""
    matched_dtou_in_controls: int = 0
    replicates: int = 0
    per_household_event_kwh: float = 0.0
    extra: dict[str, float] = field(default_factory=dict)


def _pair_means(consumption: pl.DataFrame, pairs: pl.DataFrame, role: str) -> pl.DataFrame:
    """Per event: the treated and control means on the event day and on comparison days, over the
    pairs where all four readings exist."""
    wide = consumption.filter(pl.col("role").is_in([role, f"{role}_comparison"])).pivot(
        on="role", index=["household", "event_id"], values="kwh", aggregate_function="first"
    )
    if f"{role}_comparison" not in wide.columns or role not in wide.columns:
        raise ValueError(f"no {role} readings were found for the pairs")
    t = pairs.join(wide, left_on="treated", right_on="household", how="inner").rename(
        {role: "t_event", f"{role}_comparison": "t_comp"}
    )
    both = t.join(
        wide.rename({role: "c_event", f"{role}_comparison": "c_comp"}),
        left_on=["control", "event_id"],
        right_on=["household", "event_id"],
        how="inner",
    ).drop_nulls(subset=["t_event", "t_comp", "c_event", "c_comp"])
    return both.group_by("event_id").agg(
        pl.len().alias("pairs"),
        ((pl.col("t_event") - pl.col("t_comp")) - (pl.col("c_event") - pl.col("c_comp")))
        .mean()
        .alias("did_kwh"),
        pl.col("c_event").mean().alias("control_event_kwh"),
    )


def _block_bootstrap(
    values: np.ndarray, weights: np.ndarray, plan: Plan, seed: int, name: str
) -> tuple[float, float, float, float]:
    """Weighted mean of per event values (weights: control event kWh, so the ratio is a ratio of
    means), with a block bootstrap over events in order; returns estimate, lower, upper, p."""
    n = len(values)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    estimate = float(np.sum(values) / np.sum(weights))
    block = max(1, min(plan.bootstrap_blocks, n))
    blocks = [np.arange(s, min(s + block, n)) for s in range(0, n, block)]
    generator = rng(seed, "tou", name)
    reps = []
    for _ in range(plan.bootstrap_replicates):
        chosen = generator.integers(0, len(blocks), size=len(blocks))
        idx = np.concatenate([blocks[c] for c in chosen])
        reps.append(float(np.sum(values[idx]) / np.sum(weights[idx])))
    reps_arr = np.asarray(reps)
    alpha = (1 - plan.interval_level) / 2
    lower, upper = float(np.quantile(reps_arr, alpha)), float(np.quantile(reps_arr, 1 - alpha))
    p = 2 * min(float(np.mean(reps_arr <= 0)), float(np.mean(reps_arr >= 0)))
    return estimate, lower, upper, min(p, 1.0)


def analyse(
    consumption: pl.DataFrame,
    pairs: pl.DataFrame,
    events: list[HighPriceEvent],
    seed: int,
    plan: Plan = PLAN,
) -> TouResult:
    """``consumption`` is the slot_consumption output for the households in ``pairs``."""
    if pairs.height == 0:
        raise ValueError("no matched pairs")
    treated_ids = set(pairs["treated"].to_list())
    if treated_ids & set(pairs["control"].to_list()):
        raise ValueError("a dToU household appears among the controls")
    event_means = _pair_means(consumption, pairs, "event")
    rebound_means = _pair_means(consumption, pairs, "rebound").rename(
        {"did_kwh": "rebound_kwh", "control_event_kwh": "control_rebound_kwh", "pairs": "rebound_pairs"}
    )
    meta = pl.DataFrame(
        {
            "event_id": [e.event_id for e in events],
            "event_type": [e.event_type for e in events],
            "half_hours": [e.half_hours for e in events],
            "start": [e.start for e in events],
        }
    )
    per_event = (
        meta.join(event_means, on="event_id", how="inner")
        .join(rebound_means, on="event_id", how="left")
        .with_columns(
            (pl.col("did_kwh") / pl.col("control_event_kwh")).alias("response_pct"),
            (pl.col("rebound_kwh") / pl.col("control_rebound_kwh")).alias("rebound_pct"),
            # kWh per household over the whole event: the half hourly difference times its length.
            (pl.col("did_kwh") * pl.col("half_hours")).alias("did_kwh_per_event"),
        )
        .sort("start")
    )
    if per_event.height == 0:
        raise ValueError("no event has readings for the matched pairs")
    did = per_event["did_kwh"].to_numpy()
    control = per_event["control_event_kwh"].to_numpy()
    est_pct, lo_pct, hi_pct, _ = _block_bootstrap(did, control, plan, seed, "overall_pct")
    ones = np.ones_like(did)
    per_event_kwh = per_event["did_kwh_per_event"].to_numpy()
    est_kwh, lo_kwh, hi_kwh, _ = _block_bootstrap(per_event_kwh, ones, plan, seed, "overall_kwh")
    rebound_rows = per_event.drop_nulls(subset=["rebound_kwh"])
    reb, reb_lo, reb_hi, _ = _block_bootstrap(
        rebound_rows["rebound_kwh"].to_numpy(),
        rebound_rows["control_rebound_kwh"].to_numpy(),
        plan,
        seed,
        "rebound",
    )
    rows = []
    for name, _, _ in plan.event_types:
        sub = per_event.filter(pl.col("event_type") == name)
        if sub.height == 0:
            rows.append(
                {
                    "event_type": name,
                    "events": 0,
                    "response_pct": None,
                    "lower": None,
                    "upper": None,
                    "p_value": None,
                }
            )
            continue
        e, lo, hi, p = _block_bootstrap(
            sub["did_kwh"].to_numpy(), sub["control_event_kwh"].to_numpy(), plan, seed, f"type_{name}"
        )
        rows.append(
            {
                "event_type": name,
                "events": sub.height,
                "response_pct": e,
                "lower": lo,
                "upper": hi,
                "p_value": p,
            }
        )
    by_type = pl.DataFrame(rows)
    tested = [r for r in rows if r["p_value"] is not None]
    rejected = (
        benjamini_hochberg(np.asarray([float(str(r["p_value"])) for r in tested]), plan.bh_q).tolist()
        if tested
        else []
    )
    verdicts = {str(r["event_type"]): bool(v) for r, v in zip(tested, rejected, strict=True)}
    by_type = by_type.with_columns(
        pl.col("event_type")
        .map_elements(lambda t: verdicts.get(t, False), return_dtype=pl.Boolean)
        .alias("rejected")
    )
    return TouResult(
        events=per_event.height,
        treated=len(treated_ids),
        pairs=pairs.height,
        dropped=0,
        per_event=per_event,
        overall_kwh=est_kwh,
        overall_kwh_lower=lo_kwh,
        overall_kwh_upper=hi_kwh,
        overall_pct=est_pct,
        overall_pct_lower=lo_pct,
        overall_pct_upper=hi_pct,
        rebound_pct=reb,
        rebound_pct_lower=reb_lo,
        rebound_pct_upper=reb_hi,
        by_type=by_type,
        replicates=plan.bootstrap_replicates,
        per_household_event_kwh=est_kwh,
    )
