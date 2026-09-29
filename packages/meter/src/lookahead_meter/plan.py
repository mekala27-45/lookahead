"""The pre-registered plan: its parameters, quoted from docs/tou_plan.md, and its hash."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Plan:
    pre_period_start: str = "2012-10-01"
    pre_period_end: str = "2013-01-01"
    """Exclusive."""
    comparison_days_either_side: int = 14
    rebound_hours: int = 3
    bootstrap_blocks: int = 4
    bootstrap_replicates: int = 500
    interval_level: float = 0.90
    bh_q: float = 0.05
    event_types: tuple[tuple[str, int, int], ...] = (
        ("night", 0, 6),
        ("morning", 6, 12),
        ("afternoon", 12, 17),
        ("evening", 17, 24),
    )

    def event_type(self, start_hour: int) -> str:
        for name, lo, hi in self.event_types:
            if lo <= start_hour < hi:
                return name
        raise ValueError(f"no event type for hour {start_hour}")


PLAN = Plan()


def plan_hash(path: Path) -> str:
    """SHA-256 of the committed plan document, the value the report renders."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
