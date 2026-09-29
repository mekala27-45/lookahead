"""The operating point: the alert threshold chosen on a validation year by stated costs.

For each threshold on the stated grid the detector runs over the validation year, and the cost
is the number of demand event alerts that overlap no planted load shed (false alarms, one unit
each) plus the number of planted load sheds no alert overlaps (missed events, at the stated
cost). The threshold with the lowest cost is chosen; ties go to the higher threshold, which
alerts less. The interior test says whether the choice sits strictly inside the grid; a choice
at either end means the grid, not the data, decided.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
from lookahead_core.config import POLICY

from lookahead_events.detect import find_alerts
from lookahead_events.grade import grade


@dataclass(frozen=True)
class OperatingPoint:
    threshold: float
    persistence_hours: int
    false_alarm_cost: float
    missed_event_cost: float
    cost: float
    interior: bool
    grid: tuple[float, ...]
    costs: dict[float, float] = field(default_factory=dict)
    false_alarms: dict[float, int] = field(default_factory=dict)
    missed: dict[float, int] = field(default_factory=dict)


def choose_threshold(
    standardized_validation: pl.DataFrame,
    events_validation: pl.DataFrame,
    *,
    grid: tuple[float, ...] = POLICY.alert_threshold_grid,
    persistence: int = POLICY.alert_persistence_hours,
    false_alarm_cost: float = POLICY.false_alarm_cost,
    missed_event_cost: float = POLICY.missed_event_cost,
) -> OperatingPoint:
    if len(grid) < 3:
        raise ValueError(
            "the threshold grid needs at least three points for an interior choice to mean anything"
        )
    costs: dict[float, float] = {}
    false_alarms: dict[float, int] = {}
    missed: dict[float, int] = {}
    for threshold in grid:
        alerts = find_alerts(standardized_validation, threshold, persistence)
        g = grade(alerts, events_validation)
        false_alarms[threshold] = g.false_alarms
        missed[threshold] = g.load_sheds - g.load_sheds_detected
        costs[threshold] = false_alarm_cost * g.false_alarms + missed_event_cost * missed[threshold]
    best = min(costs.values())
    chosen = max(t for t, c in costs.items() if c == best)
    ordered = sorted(grid)
    return OperatingPoint(
        threshold=chosen,
        persistence_hours=persistence,
        false_alarm_cost=false_alarm_cost,
        missed_event_cost=missed_event_cost,
        cost=best,
        interior=ordered[0] < chosen < ordered[-1],
        grid=tuple(ordered),
        costs=costs,
        false_alarms=false_alarms,
        missed=missed,
    )
