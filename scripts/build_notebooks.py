"""Write the three notebooks from source cells, so they are reviewable as code and executed by
nbmake in CI against the committed results. Each keeps a dead end on purpose.

    uv run python scripts/build_notebooks.py
    uv run pytest --nbmake notebooks
"""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks"

PRELUDE = """import json
from pathlib import Path

import numpy as np
import polars as pl

ROOT = Path.cwd() if (Path.cwd() / "results").exists() else Path.cwd().parent
manifest = json.loads((ROOT / "results" / "manifest.json").read_text(encoding="utf-8"))
values = manifest["values"]
v = lambda key: values[key]["value"]
print("as of", manifest["as_of"], "with", len(values), "values")"""

NB1 = [
    (
        "markdown",
        """# 01. The protocol and the leakage test

How the backtest is built so that it cannot flatter the model: daily origins, features at
availability through a point in time frame, a leakage test that recomputes rows at their origin,
and the deliberately leaky lag that the frame refuses. The dead end is kept at the end: the first
threshold search, which was indifferent to the threshold because the weather columns were in the
wrong units.

Every number printed here is read from the committed manifest or the committed results; nothing
is refit.""",
    ),
    ("code", PRELUDE),
    (
        "markdown",
        """## Origins, horizons and windows

One origin per day per authority at the stated issue hour, horizons 1 to 48, the last twelve
months as the test period and the twelve before as validation.""",
    ),
    (
        "code",
        """windows = json.loads((ROOT / "data" / "eia930" / "windows.json").read_text())
print({k: windows[k] for k in ("training_start", "validation_start", "test_start", "test_end")})
print("issue hour UTC", v("policy.issue_hour_utc"), "horizons", v("policy.horizons"))
print("origins in the own backtest", v("backtest.own.origins"), "fits", v("backtest.own.fits"))""",
    ),
    (
        "markdown",
        """## The frame refuses anything after the origin

`PointInTimeFrame` wraps a series and an origin; a read at or before the origin answers, a read
after it raises `LeakageError`. The same hour lag is 24 hours for the first day and 48 for the
second, because at a 00:00 origin the target hour of the second day has no yesterday yet.""",
    ),
    (
        "code",
        """from datetime import UTC, datetime, timedelta

from lookahead_features.build import same_hour_lag
from lookahead_features.frame import LeakageError, PointInTimeFrame, SeriesIndex

hours = 24 * 40
start = datetime(2025, 1, 1, tzinfo=UTC)
demand = 10_000 + 2_000 * np.sin(2 * np.pi * np.arange(hours) / 24)
series = SeriesIndex(authority="DEMO", first_hour=start, values=demand.astype(float))
origin = start + timedelta(hours=24 * 30)
frame = PointInTimeFrame(series, origin)
print("horizon 1 same hour lag", same_hour_lag(1), "horizon 30 same hour lag", same_hour_lag(30))
print("lag 24 before a target 6 hours ahead:", frame.lag(origin + timedelta(hours=6), 24))
try:
    frame.lag(origin + timedelta(hours=6), 0)
except LeakageError as e:
    print("the leaky lag was refused:", e)""",
    ),
    (
        "markdown",
        """## The recomputation test

A sample of design rows is rebuilt from the raw series through the frame and compared with the
vectorized design; the registry's leakage gate runs the same function on a real authority.""",
    ),
    (
        "code",
        """from lookahead_features.build import FeatureSpec
from lookahead_features.leakage import recomputation_check

rng = np.random.default_rng(0)
temperature = 10 + 12 * np.sin(2 * np.pi * np.arange(hours) / 24) + rng.normal(0, 1, hours)
humidity = np.full(hours, 60.0)
offsets = np.full(hours, -5)
origins = np.array([24 * d for d in range(20, 39)])
report = recomputation_check(series, temperature, humidity, offsets, FeatureSpec(), 10_000.0, origins, seed=1)
print("rows checked", report.rows_checked, "largest gap", report.max_abs_gap, "leaky lag refused", report.leaky_lag_refused, "green", report.green)""",
    ),
    (
        "markdown",
        """## The dead end: a threshold search that could not see the threshold

The first own model put raw degree hours beside a ratio target. On the simulator, where the true
heating threshold is known, the validation MAPE was flat across the candidate thresholds, so the
search picked whichever came first. Scaling the weather columns by the authority's typical demand
and replacing the raw temperature with the change in degree hours against the same hour lag made
the search recover the truth. The committed search grid shows the current spread across
thresholds for one real authority: the search now has something to choose.""",
    ),
    (
        "code",
        """search = pl.read_parquet(ROOT / "results" / "backtest" / "own" / "threshold_search.parquet")
one = search.filter(pl.col("authority") == search["authority"][0])
best_penalty = one.sort("validation_mape")["penalty"][0]
grid = one.filter(pl.col("penalty") == best_penalty).pivot(on="cooling", index="heating", values="validation_mape")
print(one["authority"][0], "penalty", best_penalty)
print(grid)
spread = float(one["validation_mape"].max() - one["validation_mape"].min())
print("spread of validation MAPE across the grid:", round(spread, 4), "(a flat grid was the bug)")""",
    ),
    (
        "markdown",
        """The chosen thresholds per authority are in the manifest, and the protocol test holds every
choice to the validation year.""",
    ),
    (
        "code",
        """print("chosen on validation:", v("backtest.own.chosen_on_validation"))
print("own MAPE", v("backtest.own.mape"), "seasonal naive", v("backtest.own.mape_naive"), "operator", v("backtest.own.mape_operator"))""",
    ),
]

NB2 = [
    (
        "markdown",
        """# 02. Reconciliation

The hierarchy from the lower 48 to the subregion, three methods, coherence to the megawatt, and
the honest result by level. The dead end kept here: top down by historical proportions, which
made the leaves worse, as the table shows.""",
    ),
    ("code", PRELUDE),
    (
        "markdown",
        """## The summing matrix

Built from `data/hierarchy.csv` with a remainder node per authority that has subregions, so the
leaves sum to their authority without any series being rescaled.""",
    ),
    (
        "code",
        """nodes = pl.read_csv(ROOT / "results" / "hierarchy" / "nodes.csv")
print(nodes.group_by("kind").len().sort("kind"))
from lookahead_hierarchy.summing import SummingMatrix
summing = SummingMatrix.from_table(nodes)
print("nodes", len(summing.nodes), "leaves", len(summing.leaves), "matrix", summing.matrix.shape)""",
    ),
    ("markdown", """## Coherence and accuracy by level"""),
    (
        "code",
        """coherence = json.loads((ROOT / "results" / "hierarchy" / "coherence.json").read_text())
print("coherence gaps in MW:", coherence["gaps_mw"])
scores = pl.read_parquet(ROOT / "results" / "hierarchy" / "scores_by_level.parquet")
print(scores.select("method", "level_name", "mape", "mape_lower", "mape_upper", "coverage_90").sort(["level", "method"]))""",
    ),
    (
        "markdown",
        """## The dead end: top down hurts the leaves

Splitting the top forecast by the validation year's proportions ignores everything the leaf
models know, and the remainder nodes make the proportions noisy. It is kept in the table and on
the page because the morning meeting reads the leaves too.""",
    ),
    (
        "code",
        """base = scores.filter(pl.col("method") == "base").sort("level")
for method in ("bottom_up", "top_down", "mint"):
    m = scores.filter(pl.col("method") == method).sort("level")
    change = (m["mape"] - base["mape"]).to_list()
    print(method, "change in MAPE by level (negative helps):", [round(c, 4) for c in change])
print("helped:", v("hierarchy.helped_list"))
print("hurt:", v("hierarchy.hurt_list"))""",
    ),
    (
        "markdown",
        """## Against the truth, on the simulator

On the simulator the reconciliation is scored against the true demand rather than the observed
actuals, by condition and seed.""",
    ),
    (
        "code",
        """summary = pl.read_parquet(ROOT / "results" / "recovery" / "summary.parquet")
print(summary.filter(pl.col("figure").str.starts_with("reconciliation.mint_gain")).select("condition", "figure", "mean", "lower", "upper"))""",
    ),
]

NB3 = [
    (
        "markdown",
        """# 03. Events and the meter

The detector on the real test year and on the known events, then the meter's clusters and the
time of use response. The dead end kept here: a detector graded on the known events without a
persistence rule, which would have raised an alert on every noisy hour.""",
    ),
    ("code", PRELUDE),
    ("markdown", """## The operating point"""),
    (
        "code",
        """point = json.loads((ROOT / "results" / "events" / "operating_point.json").read_text())
print({k: point[k] for k in ("threshold", "persistence_hours", "false_alarm_cost", "missed_event_cost", "cost", "interior")})
print("costs by threshold:", point["costs"])""",
    ),
    ("markdown", """## The known events"""),
    (
        "code",
        """known = pl.read_parquet(ROOT / "results" / "events" / "known_events.parquet")
print(known.select("event", "node", "onset_utc", "detected", "delay_hours", "peak_z", "false_alarms_in_window"))
print("recall", v("events.known.recall"), "missed:", v("events.known.missed_list"))""",
    ),
    (
        "markdown",
        """## The dead end: no persistence rule

With the persistence rule removed (one hour past the threshold is an alert), the same standardized
residuals in the known event windows raise many more alerts outside the events. The stated rule
costs a few hours of delay and buys the false alarm rate on the page.""",
    ),
    (
        "code",
        """from lookahead_events.detect import find_alerts

windows = pl.read_parquet(ROOT / "results" / "events" / "known_event_windows.parquet")
frame = windows.with_columns(pl.col("flagged").fill_null(False)).rename({"utc_hour": "utc_hour"})
frame = frame.with_columns(pl.lit(None, dtype=pl.Float64).alias("residual_center"), pl.lit(None, dtype=pl.Float64).alias("residual_scale"), pl.lit(None, dtype=pl.Float64).alias("residual"))
with_rule = find_alerts(frame, point["threshold"], point["persistence_hours"])
without = find_alerts(frame, point["threshold"], 1)
print("demand event alerts in the known event windows: with the rule", sum(a.kind == "demand_event" for a in with_rule), "without", sum(a.kind == "demand_event" for a in without))""",
    ),
    ("markdown", """## The meter"""),
    (
        "code",
        """clusters = pl.read_parquet(ROOT / "results" / "meter" / "clusters.parquet")
print(clusters)
plan = json.loads((ROOT / "results" / "meter" / "plan.json").read_text())
print("plan hash", plan["sha256"][:16], "events", plan["events"], "pairs", plan["pairs"])
print("response", v("meter.tou.response_pct"), "interval", v("meter.tou.response_pct_lower"), v("meter.tou.response_pct_upper"))
print(pl.read_parquet(ROOT / "results" / "meter" / "tou_by_type.parquet"))""",
    ),
]


def build(name: str, cells: list[tuple[str, str]]) -> None:
    nb = nbformat.v4.new_notebook()
    nb["metadata"]["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    nb["cells"] = [
        nbformat.v4.new_markdown_cell(text) if kind == "markdown" else nbformat.v4.new_code_cell(text)
        for kind, text in cells
    ]
    OUT.mkdir(exist_ok=True)
    nbformat.write(nb, OUT / name)


def main() -> int:
    build("01_protocol_and_leakage.ipynb", NB1)
    build("02_reconciliation.ipynb", NB2)
    build("03_events_and_the_meter.ipynb", NB3)
    print("wrote three notebooks under notebooks/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
