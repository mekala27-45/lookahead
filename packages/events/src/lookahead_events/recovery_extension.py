"""The detector graded on the simulator inside the recovery study.

Per condition and seed: the threshold is chosen on the validation year (where the simulator
plants one event of each kind per authority) by the stated costs, then the detector runs over
the test year and is graded on the events planted there. Reports the chosen threshold and
whether it was interior, recall on the planted load sheds and on the planted defects,
precision on demand event alerts, the false alarm count, the defects reported as events (the
figure that has to be zero) and the mean detection delay.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
from lookahead_core.config import POLICY
from lookahead_evaluation import recovery
from lookahead_forecast.interface import PanelData

from lookahead_events.detect import FLAG_COLUMNS, ResidualScale, find_alerts, residual_scale, standardize
from lookahead_events.grade import grade
from lookahead_events.operating import choose_threshold

SHORT_HORIZON = 24


def validation_frame(fitted: Any, data: PanelData) -> tuple[pl.DataFrame, dict[str, ResidualScale]]:
    """The own backend's expanding validation run as a detector frame (authority, utc_hour, pred)
    at horizons 1 to 24, with the residual scale per authority from the same rows."""
    frames = []
    scales: dict[str, ResidualScale] = {}
    for authority in data.names:
        run = fitted.validation[authority]
        a = data.authorities[authority]
        keep = run.horizon <= SHORT_HORIZON
        target = run.origin_position[keep] + run.horizon[keep]
        pred = run.pred_ratio[keep] * run.scale[keep]
        actual = run.actual_ratio[keep] * run.scale[keep]
        ok = np.isfinite(pred) & (pred > 0) & np.isfinite(actual)
        scales[authority] = residual_scale((actual[ok] - pred[ok]) / pred[ok])
        frames.append(
            pl.DataFrame(
                {
                    "authority": [authority] * int(keep.sum()),
                    "utc_hour": pl.Series(
                        [a.series.hour_at(int(t)) for t in target], dtype=pl.Datetime("us", "UTC")
                    ),
                    "pred": pred,
                }
            )
        )
    return pl.concat(frames), scales


def test_frame(scoring: pl.DataFrame) -> pl.DataFrame:
    """The backtest's scoring rows at horizons 1 to 24 as a detector frame."""
    return (
        scoring.filter(pl.col("horizon") <= SHORT_HORIZON)
        .select("authority", pl.col("target_hour").alias("utc_hour"), pl.col("q50").alias("pred"))
        .sort(["authority", "utc_hour"])
    )


def attach_raw(frame: pl.DataFrame, panel: pl.DataFrame) -> pl.DataFrame:
    """Join the raw demand and the quarantine flags from the panel onto the detector frame."""
    flags = [c for c in FLAG_COLUMNS if c in panel.columns]
    raw = panel.select("authority", "utc_hour", "demand_raw", *flags)
    return frame.join(raw, on=["authority", "utc_hour"], how="left")


def detector_on_sim(
    data: PanelData,
    panel: pl.DataFrame,
    subregions: pl.DataFrame,
    hierarchy: pl.DataFrame,
    extras: dict[str, Any],
    seed: int,
) -> dict[str, float]:
    fitted = extras["own_fitted"]
    events: pl.DataFrame = extras["events"]
    validation_events = (
        events.filter(pl.col("window") == "validation") if "window" in events.columns else events.head(0)
    )
    test_events = events.filter(pl.col("window") == "test") if "window" in events.columns else events
    frame_val, scales = validation_frame(fitted, data)
    standardized_val = standardize(attach_raw(frame_val, panel), scales)
    point = choose_threshold(standardized_val, validation_events)
    standardized_test = standardize(attach_raw(test_frame(extras["own_scoring"]), panel), scales)
    alerts = find_alerts(standardized_test, point.threshold, POLICY.alert_persistence_hours)
    g = grade(alerts, test_events)
    out = {
        "threshold": point.threshold,
        "interior": 1.0 if point.interior else 0.0,
        "validation_cost": point.cost,
        "recall_load_shed": g.recall_load_shed,
        "recall_defects": g.recall_defects,
        "precision_demand_events": g.precision_demand_events if g.demand_alerts else 1.0,
        "false_alarms": float(g.false_alarms),
        "defects_called_events": float(g.defects_called_events),
        "demand_alerts": float(g.demand_alerts),
        "defect_alerts": float(g.defect_alerts),
        "mean_delay_hours": g.mean_delay_hours if g.delays_hours else float("nan"),
    }
    _ = (subregions, hierarchy, seed)
    return out


def register() -> None:
    recovery.EXTENSIONS.setdefault("detector", detector_on_sim)
