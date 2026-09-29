"""The detector: classification by rule, the persistence rule, the operating point's interior
test, grading, and the known events table's dates."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from lookahead_core.config import POLICY
from lookahead_events import (
    ResidualScale,
    choose_threshold,
    classify_run,
    find_alerts,
    grade,
    residual_scale,
    standardize,
)

ROOT = Path(__file__).resolve().parents[2]
HOUR = timedelta(hours=1)
START = datetime(2025, 1, 1, tzinfo=UTC)


def _frame(z_values: list[float], flagged: list[bool] | None = None, authority: str = "A") -> pl.DataFrame:
    """A detector frame whose standardized residual equals z_values: pred 100, scale 0.01, center 0."""
    n = len(z_values)
    flagged = flagged or [False] * n
    raw = [None if f else 100.0 * (1 + 0.01 * z) for z, f in zip(z_values, flagged, strict=True)]
    frame = pl.DataFrame(
        {
            "authority": [authority] * n,
            "utc_hour": pl.Series([START + HOUR * i for i in range(n)], dtype=pl.Datetime("us", "UTC")),
            "pred": [100.0] * n,
            "demand_raw": raw,
            "demand_missing": flagged,
        }
    )
    return standardize(frame, {authority: ResidualScale(center=0.0, scale=0.01, rows=1000)})


def test_a_dead_feed_is_a_defect_and_a_drop_is_an_event() -> None:
    zeros = np.array([True, True, True, True])
    assert classify_run(zeros, np.full(4, np.nan), neighbors_normal=True) == "data_defect"
    assert classify_run(zeros, np.full(4, np.nan), neighbors_normal=False) == "data_defect"
    drop = np.array([False, False, False, False])
    assert classify_run(drop, np.array([-6.0, -7.0, -6.5, -8.0]), neighbors_normal=True) == "demand_event"
    with pytest.raises(ValueError):
        classify_run(np.array([], dtype=bool), np.array([]), neighbors_normal=True)


def test_persistence_rule_needs_the_stated_hours() -> None:
    quiet = [0.2, -0.5, 0.1] * 10
    two = quiet[:10] + [6.0, 6.5] + quiet[10:]
    three = quiet[:10] + [6.0, 6.5, 7.0] + quiet[10:]
    assert find_alerts(_frame(two), threshold=5.0, persistence=3) == []
    alerts = find_alerts(_frame(three), threshold=5.0, persistence=3)
    assert len(alerts) == 1
    assert alerts[0].kind == "demand_event" and alerts[0].direction == "high" and alerts[0].hours == 3
    assert alerts[0].start == START + HOUR * 10
    with pytest.raises(ValueError):
        find_alerts(_frame(three), threshold=0.0, persistence=3)


def test_flagged_hours_alert_as_defects_at_any_length() -> None:
    z = [0.1] * 20
    flagged = [False] * 20
    flagged[8] = True
    alerts = find_alerts(_frame(z, flagged), threshold=5.0, persistence=3)
    assert len(alerts) == 1 and alerts[0].kind == "data_defect" and alerts[0].hours == 1
    assert alerts[0].flags == "demand_missing"


def test_a_defect_next_to_a_drop_is_still_not_an_event() -> None:
    # Three zero hours inside a real drop: the run is a demand event with flagged hours in it,
    # never a defect pretending to be a collapse, and a pure zero run stays a defect.
    z = [0.0] * 5 + [-7.0, -7.0, 0.0, 0.0, 0.0, -7.0, -7.0] + [0.0] * 5
    flagged = [False] * 5 + [False, False, True, True, True, False, False] + [False] * 5
    alerts = find_alerts(_frame(z, flagged), threshold=5.0, persistence=3)
    assert len(alerts) == 1 and alerts[0].kind == "demand_event" and alerts[0].flagged_hours == 3


def test_residual_scale_is_robust_and_refuses_too_few_rows() -> None:
    rng = np.random.default_rng(0)
    r = rng.normal(0.0, 0.02, size=5000)
    r[:50] = 5.0  # gross outliers barely move a median based scale
    scale = residual_scale(r)
    assert abs(scale.scale - 0.02) < 0.003 and abs(scale.center) < 0.003
    with pytest.raises(ValueError):
        residual_scale(np.zeros(50))


def _validation_with_sheds(threshold_shape: float) -> tuple[pl.DataFrame, pl.DataFrame]:
    """A year of standardized residuals with structural excursions of size threshold_shape and two
    planted load sheds of z -5.5: a threshold of 5 catches them without the excursions, one of 6
    misses them, so the cost minimum sits strictly inside the grid."""
    rng = np.random.default_rng(1)
    z = rng.normal(0, 1, size=24 * 200).tolist()
    for start in range(100, len(z) - 10, 400):
        for k in range(4):
            z[start + k] = threshold_shape
    sheds = []
    for start in (1000, 3000):
        for k in range(8):
            z[start + k] = -5.5
        sheds.append(start)
    frame = _frame(z)
    events = pl.DataFrame(
        {
            "kind": ["load_shed", "load_shed"],
            "authority": ["A", "A"],
            "start_utc": pl.Series([START + HOUR * s for s in sheds], dtype=pl.Datetime("us", "UTC")),
            "duration_hours": [8, 8],
            "size_share": [0.2, 0.2],
        }
    )
    return frame, events


def test_operating_point_is_chosen_by_cost_and_is_interior() -> None:
    frame, events = _validation_with_sheds(threshold_shape=4.2)
    point = choose_threshold(frame, events, grid=(2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0))
    assert point.threshold == 5.0
    assert point.interior
    assert point.missed[5.0] == 0 and point.false_alarms[5.0] == 0
    assert point.false_alarms[4.0] > 0, "the structural excursions are false alarms below the choice"
    assert point.missed[6.0] == 2, "a threshold above the sheds misses them"
    assert point.cost == 0.0


def test_operating_point_at_the_edge_fails_the_interior_test() -> None:
    frame, events = _validation_with_sheds(threshold_shape=4.2)
    point = choose_threshold(frame, events, grid=(5.0, 6.0, 7.0))
    assert point.threshold == 5.0 and not point.interior
    with pytest.raises(ValueError):
        choose_threshold(frame, events, grid=(5.0, 6.0))


def test_missed_events_cost_more_than_false_alarms() -> None:
    frame, events = _validation_with_sheds(threshold_shape=4.2)
    # With sheds at z -5.5 and a grid that starts above them, every threshold misses both; the cost
    # is then two missed events at the stated price and the choice is the largest tied threshold.
    point = choose_threshold(frame, events, grid=(9.0, 10.0, 11.0))
    assert point.cost == 2 * POLICY.missed_event_cost
    assert point.threshold == 11.0


def test_grade_counts_detections_false_alarms_and_misclassified_defects() -> None:
    z = [0.0] * 30
    flagged = [False] * 30
    for k in range(5, 9):
        z[k] = -7.0
    for k in range(15, 18):
        flagged[k] = True
    for k in range(22, 25):
        z[k] = 6.0
    alerts = find_alerts(_frame(z, flagged), threshold=5.0, persistence=3)
    events = pl.DataFrame(
        {
            "kind": ["load_shed", "meter_zero", "load_shed"],
            "authority": ["A", "A", "A"],
            "start_utc": pl.Series(
                [START + HOUR * 5, START + HOUR * 15, START + HOUR * 28], dtype=pl.Datetime("us", "UTC")
            ),
            "duration_hours": [4, 3, 2],
            "size_share": [0.2, 0.0, 0.2],
        }
    )
    g = grade(alerts, events)
    assert g.load_sheds == 2 and g.load_sheds_detected == 1
    assert g.defects == 1 and g.defects_recovered == 1 and g.defects_called_events == 0
    assert g.demand_alerts == 2 and g.false_alarms == 1
    assert g.recall_load_shed == 0.5 and g.precision_demand_events == 0.5
    assert g.delays_hours == [0.0]


def test_known_events_table_is_inside_the_data_window_with_a_citation_each() -> None:
    table = pl.read_csv(ROOT / "data" / "known_events.csv", try_parse_dates=True)
    windows = json.loads((ROOT / "data" / "eia930" / "windows.json").read_text(encoding="utf-8"))
    first = datetime.fromisoformat(str(windows["training_start"]))
    last = datetime.fromisoformat(str(windows["test_end"]))
    assert table.height >= 5
    assert table["event"].n_unique() == 5, "the five named events of the brief"
    for row in table.iter_rows(named=True):
        assert first <= row["onset_utc"].replace(tzinfo=None) <= last, row["event"]
        assert row["onset_utc"] < row["end_utc"], row["event"]
        assert "http" in row["citation"], row["event"]
        assert row["node"].split(".")[0] == row["authority"]


@pytest.mark.slow
def test_planted_defects_are_recovered_and_never_called_events() -> None:
    """On the demonstration grid every planted defect comes back as a defect and no defect is
    reported as a demand event; the operating point chosen on validation is interior."""
    import lookahead_events  # noqa: F401
    from lookahead_evaluation.recovery import run_one

    record = run_one("base", 0)
    f = record.figures
    assert f["detector.recall_defects"] == 1.0
    assert f["detector.defects_called_events"] == 0.0
    assert f["detector.interior"] == 1.0
    assert 0.0 <= f["detector.recall_load_shed"] <= 1.0
