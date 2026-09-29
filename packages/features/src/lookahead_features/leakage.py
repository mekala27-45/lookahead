"""The leakage check as a library call, so the registry gate and the test run the same code.

A sample of design rows is recomputed from the raw series at their origin through the point in
time frame, which cannot read past the origin, and compared with the design's rows; and the
deliberately leaky lag (the target hour's own demand) is asked for and has to be refused.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from lookahead_features.build import FeatureSpec, design, row_from_frame, same_hour_lag
from lookahead_features.frame import LeakageError, PointInTimeFrame, SeriesIndex


@dataclass(frozen=True)
class LeakageReport:
    rows_checked: int
    max_abs_gap: float
    leaky_lag_refused: bool
    tolerance: float = 1e-9

    @property
    def green(self) -> bool:
        return self.rows_checked > 0 and self.max_abs_gap <= self.tolerance and self.leaky_lag_refused


def recomputation_check(
    series: SeriesIndex,
    temperature: np.ndarray,
    humidity: np.ndarray,
    offsets: np.ndarray,
    spec: FeatureSpec,
    typical_mw: float,
    origins: np.ndarray,
    seed: int,
    samples: int = 60,
) -> LeakageReport:
    if len(origins) == 0:
        raise ValueError("the leakage check needs at least one origin")
    horizons = np.arange(1, 49)
    d = design(series, origins, horizons, offsets, temperature, humidity, spec, typical_mw)
    usable = np.flatnonzero(d.usable)
    if len(usable) == 0:
        raise ValueError("no usable design row to check")
    rng = np.random.default_rng(seed)
    picks = rng.choice(usable, size=min(samples, len(usable)), replace=False)
    worst = 0.0
    for i in sorted(int(p) for p in picks):
        origin = series.hour_at(int(d.origin_position[i]))
        frame = PointInTimeFrame(series, origin)
        h = int(d.horizon[i])
        t = int(d.target_position[i])
        lag_t = t - same_hour_lag(h)
        row, _ = row_from_frame(
            frame,
            h,
            int(offsets[t]),
            float(temperature[t]),
            float(humidity[t]),
            spec,
            typical_mw,
            float(temperature[lag_t]) if lag_t >= 0 else float("nan"),
        )
        worst = max(worst, float(np.max(np.abs(d.x[i] - row))))
    # The deliberately leaky feature: the target hour's own value, which is after the origin.
    origin = series.hour_at(int(d.origin_position[int(picks[0])]))
    frame = PointInTimeFrame(series, origin)
    target = origin + (series.hour_at(1) - series.hour_at(0)) * int(d.horizon[int(picks[0])])
    refused = False
    try:
        frame.lag(target, 0)
    except LeakageError:
        refused = True
    return LeakageReport(rows_checked=len(picks), max_abs_gap=worst, leaky_lag_refused=refused)
