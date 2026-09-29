"""Grading against events the detector never saw: planted events on the simulator, known events
on the real grid. A planted load shed is detected when a demand event alert overlaps its hours;
a planted defect is recovered when a data defect alert overlaps its hours; a demand event alert
that overlaps no load shed is a false alarm; a planted defect overlapped only by a demand event
alert is a defect reported as an event, which the tests require to be zero."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import polars as pl

from lookahead_events.detect import Alert

HOUR = timedelta(hours=1)
DEFECT_KINDS = ("meter_zero", "duplicate_hour", "skipped_hours")


@dataclass
class Grade:
    load_sheds: int = 0
    load_sheds_detected: int = 0
    defects: int = 0
    defects_recovered: int = 0
    defects_called_events: int = 0
    demand_alerts: int = 0
    defect_alerts: int = 0
    false_alarms: int = 0
    delays_hours: list[float] = field(default_factory=list)
    detections: list[dict[str, Any]] = field(default_factory=list)

    @property
    def recall_load_shed(self) -> float:
        return self.load_sheds_detected / self.load_sheds if self.load_sheds else float("nan")

    @property
    def recall_defects(self) -> float:
        return self.defects_recovered / self.defects if self.defects else float("nan")

    @property
    def precision_demand_events(self) -> float:
        return (
            (self.demand_alerts - self.false_alarms) / self.demand_alerts
            if self.demand_alerts
            else float("nan")
        )

    @property
    def mean_delay_hours(self) -> float:
        return sum(self.delays_hours) / len(self.delays_hours) if self.delays_hours else float("nan")


def grade(alerts: list[Alert], events: pl.DataFrame) -> Grade:
    """``events`` has kind, authority, start_utc and duration_hours (the simulator's frame) or
    kind, authority, onset_utc and end_utc (the known events table)."""
    g = Grade()
    spans: list[tuple[str, str, datetime, datetime, str]] = []
    for row in events.iter_rows(named=True):
        start = row.get("start_utc") or row.get("onset_utc")
        if not isinstance(start, datetime):
            raise ValueError("every event needs a start_utc or onset_utc datetime")
        end_value = row.get("end_utc")
        end = (
            end_value if isinstance(end_value, datetime) else start + HOUR * (int(row["duration_hours"]) - 1)
        )
        spans.append(
            (str(row["kind"]), str(row["authority"]), start, end, str(row.get("event", row["kind"])))
        )
    matched_alerts: set[int] = set()
    for kind, authority, start, end, label in spans:
        same = [
            (i, a)
            for i, a in enumerate(alerts)
            if a.authority == authority and a.start <= end + HOUR and a.end >= start - HOUR
        ]
        demand_hits = [(i, a) for i, a in same if a.kind == "demand_event"]
        defect_hits = [(i, a) for i, a in same if a.kind == "data_defect"]
        if kind in DEFECT_KINDS:
            g.defects += 1
            if defect_hits:
                g.defects_recovered += 1
                matched_alerts.update(i for i, _ in defect_hits)
            elif demand_hits:
                g.defects_called_events += 1
            g.detections.append(
                {
                    "event": label,
                    "kind": kind,
                    "authority": authority,
                    "onset": start,
                    "detected": bool(defect_hits),
                    "detection_hour": defect_hits[0][1].start if defect_hits else None,
                    "delay_hours": (defect_hits[0][1].start - start) / HOUR if defect_hits else None,
                    "peak_z": defect_hits[0][1].peak_z if defect_hits else None,
                }
            )
        else:
            g.load_sheds += 1
            if demand_hits:
                g.load_sheds_detected += 1
                first = min(demand_hits, key=lambda x: x[1].start)[1]
                delay = (first.start - start) / HOUR
                g.delays_hours.append(delay)
                matched_alerts.update(i for i, _ in demand_hits)
            g.detections.append(
                {
                    "event": label,
                    "kind": kind,
                    "authority": authority,
                    "onset": start,
                    "detected": bool(demand_hits),
                    "detection_hour": min(a.start for _, a in demand_hits) if demand_hits else None,
                    "delay_hours": (min(a.start for _, a in demand_hits) - start) / HOUR
                    if demand_hits
                    else None,
                    "peak_z": max(a.peak_z for _, a in demand_hits) if demand_hits else None,
                }
            )
    g.demand_alerts = sum(1 for a in alerts if a.kind == "demand_event")
    g.defect_alerts = sum(1 for a in alerts if a.kind == "data_defect")
    g.false_alarms = sum(
        1 for i, a in enumerate(alerts) if a.kind == "demand_event" and i not in matched_alerts
    )
    return g
