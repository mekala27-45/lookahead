"""Base forecasts at every node, three reconciliations, accuracy by level before and after.

The own backend forecasts every node directly over the test year (the aggregates as well
as the leaves, so top down and MinT have something to reconcile). The base forecasts are
laid out as rows of (origin, horizon) common to every node, by nodes, by levels. Each method
yields a coherent set, checked to the megawatt. Accuracy is measured per level against
each node's own actuals, before and after each method, with block bootstrap intervals over
days, and the callout says where a method helped and where it hurt.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import polars as pl
from lookahead_core.config import POLICY
from lookahead_evaluation.bootstrap import bootstrap_statistic, resample_day_sums
from lookahead_evaluation.harness import run_backend
from lookahead_forecast.interface import QUANTILE_COLUMNS, ForecastSpec, PanelData
from lookahead_forecast.own import OwnForecaster

from lookahead_hierarchy.reconcile import (
    bottom_up,
    historical_proportions,
    mint,
    reconcile_quantiles,
    shrink_covariance,
    top_down,
)
from lookahead_hierarchy.summing import SummingMatrix, check_coherent

METHODS = ("base", "bottom_up", "top_down", "mint")
LEVEL_NAMES = {0: "lower 48", 1: "interconnection", 2: "region", 3: "authority", 4: "subregion"}


@dataclass
class LevelScore:
    method: str
    level: int
    nodes: int
    rows: int
    mape: float
    mape_lower: float
    mape_upper: float
    coverage_90: float
    mape_by_node: dict[str, float] = field(default_factory=dict)


@dataclass
class StudyResult:
    summing: SummingMatrix
    scores: list[LevelScore]
    coherence_gap_mw: dict[str, float]
    shrinkage_intensity: float
    rows: int
    origins: int
    reconciled: dict[str, np.ndarray]
    """Method to rows by nodes by levels, in megawatts."""
    keys: pl.DataFrame
    """The (origin, horizon, target_hour) of every row."""
    actual: np.ndarray
    origin_day: np.ndarray
    base_scoring: pl.DataFrame


def _aligned(frame: pl.DataFrame, nodes: list[str]) -> tuple[pl.DataFrame, np.ndarray, np.ndarray]:
    """Rows of (origin, horizon) present for every node; returns keys, quantiles (rows, nodes, levels), actual (rows, nodes)."""
    keys = frame.select("origin", "horizon", "target_hour").unique().sort(["origin", "horizon"])
    counts = frame.group_by(["origin", "horizon"]).len()
    full = counts.filter(pl.col("len") == len(nodes)).select("origin", "horizon")
    keys = keys.join(full, on=["origin", "horizon"], how="inner").sort(["origin", "horizon"])
    q = np.empty((keys.height, len(nodes), len(QUANTILE_COLUMNS)))
    actual = np.empty((keys.height, len(nodes)))
    for j, node in enumerate(nodes):
        sub = keys.join(
            frame.filter(pl.col("authority") == node), on=["origin", "horizon", "target_hour"], how="left"
        )
        for k, c in enumerate(QUANTILE_COLUMNS):
            q[:, j, k] = sub[c].cast(pl.Float64).fill_null(float("nan")).to_numpy()
        actual[:, j] = sub["actual"].cast(pl.Float64).fill_null(float("nan")).to_numpy()
    return keys, q, actual


def run_study(
    data: PanelData, summing: SummingMatrix, seed: int, spec: ForecastSpec | None = None
) -> StudyResult:
    spec = spec or ForecastSpec(backend="own", seed=seed)
    forecaster = OwnForecaster()
    nodes = summing.nodes
    # The remainder nodes hold an authority's difference from its subregions: near zero, at times
    # negative, so no ratio model is fit to them. Their base median, their actuals and their
    # validation residuals are the parent's minus the siblings', so bottom up reproduces the
    # authority's own median exactly; they carry no interval of their own and are not scored.
    series = summing.series
    result = run_backend(_only(data, series), forecaster, spec)
    keys, base, actual = _aligned(result.scoring, series)
    base, actual = _with_remainders(base, actual, series, summing)
    finite = np.all(np.isfinite(base), axis=(1, 2))
    keys, base, actual = keys.filter(pl.Series(finite)), base[finite], actual[finite]
    rows = base.shape[0]
    if rows == 0:
        raise ValueError("no row has a base forecast for every node")

    # Validation residuals in megawatts, aligned across nodes, for the MinT covariance.
    fitted = result.fitted
    residual_frames = []
    for node in series:
        v = fitted.validation[node]
        residual_frames.append(
            pl.DataFrame(
                {
                    "origin_position": v.origin_position,
                    "horizon": v.horizon,
                    node: (v.actual_ratio - v.pred_ratio) * v.scale,
                }
            )
        )
    aligned = _derive_remainders(_join_all(residual_frames), summing)
    residuals = aligned.select(nodes).to_numpy().astype(np.float64)
    covariance, intensity = shrink_covariance(residuals)

    # Top down proportions from the validation year's actual leaves.
    leaf_nodes = summing.leaves
    validation_actual = []
    for node in series:
        v = fitted.validation[node]
        validation_actual.append(
            pl.DataFrame(
                {"origin_position": v.origin_position, "horizon": v.horizon, node: v.actual_ratio * v.scale}
            )
        )
    leaf_aligned = _derive_remainders(_join_all(validation_actual), summing)
    proportions = historical_proportions(leaf_aligned.select(leaf_nodes).to_numpy().astype(np.float64))

    reconciled: dict[str, np.ndarray] = {"base": base}
    gaps: dict[str, float] = {}
    reconciled["bottom_up"] = reconcile_quantiles(base, summing, "bottom_up")
    reconciled["top_down"] = reconcile_quantiles(base, summing, "top_down", proportions=proportions)
    reconciled["mint"] = reconcile_quantiles(base, summing, "mint", covariance=covariance)
    median = QUANTILE_COLUMNS.index("q50")
    for method in ("bottom_up", "top_down", "mint"):
        gaps[method] = check_coherent(reconciled[method][:, :, median], summing)
    try:
        gaps["base"] = check_coherent(base[:, :, median], summing)
    except Exception:
        leaves_sum = summing.aggregate(base[:, summing.leaf_index, median])
        gaps["base"] = float(np.nanmax(np.abs(leaves_sum - base[:, :, median])))

    origin_day = keys.select((pl.col("origin") - pl.duration(hours=1)).dt.date().alias("day"))[
        "day"
    ].to_numpy()
    scores = _score(reconciled, actual, origin_day, summing, seed)
    return StudyResult(
        summing=summing,
        scores=scores,
        coherence_gap_mw=gaps,
        shrinkage_intensity=intensity,
        rows=rows,
        origins=int(keys["origin"].n_unique()),
        reconciled=reconciled,
        keys=keys,
        actual=actual,
        origin_day=origin_day,
        base_scoring=result.scoring,
    )


def _only(data: PanelData, names: list[str]) -> PanelData:
    """The panel restricted to the named nodes."""
    return replace(
        data,
        authorities={n: data.authorities[n] for n in names},
        truth={n: v for n, v in data.truth.items() if n in names},
    )


def _join_all(frames: list[pl.DataFrame]) -> pl.DataFrame:
    out = frames[0]
    for f in frames[1:]:
        out = out.join(f, on=["origin_position", "horizon"], how="inner")
    return out


def _derive_remainders(frame: pl.DataFrame, summing: SummingMatrix) -> pl.DataFrame:
    """Add a column per remainder node: the parent's column minus the siblings'."""
    for node in summing.remainders:
        parent = summing.parents[node]
        siblings = summing.siblings(node)
        expr = pl.col(str(parent))
        for sibling in siblings:
            expr = expr - pl.col(sibling)
        frame = frame.with_columns(expr.alias(node))
    return frame


def _with_remainders(
    base: np.ndarray, actual: np.ndarray, series: list[str], summing: SummingMatrix
) -> tuple[np.ndarray, np.ndarray]:
    """Widen the aligned arrays from the series nodes to every node, deriving each remainder's
    median and actual as the parent's minus the siblings'. The remainder's five levels all equal
    its median: a difference of quantiles is not a quantile of the difference, and a bookkeeping
    node has no interval to publish."""
    nodes = summing.nodes
    full_base = np.full((base.shape[0], len(nodes), base.shape[2]), np.nan)
    full_actual = np.full((actual.shape[0], len(nodes)), np.nan)
    index = {n: j for j, n in enumerate(series)}
    for j, node in enumerate(nodes):
        if node in index:
            full_base[:, j, :] = base[:, index[node], :]
            full_actual[:, j] = actual[:, index[node]]
    for node in summing.remainders:
        parent = str(summing.parents[node])
        siblings = summing.siblings(node)
        j = nodes.index(node)
        median = QUANTILE_COLUMNS.index("q50")
        rest = base[:, index[parent], median] - sum(base[:, index[s], median] for s in siblings)
        full_base[:, j, :] = rest[:, None]
        full_actual[:, j] = actual[:, index[parent]] - sum(actual[:, index[s]] for s in siblings)
    return full_base, full_actual


def _score(
    reconciled: dict[str, np.ndarray],
    actual: np.ndarray,
    origin_day: np.ndarray,
    summing: SummingMatrix,
    seed: int,
) -> list[LevelScore]:
    scores: list[LevelScore] = []
    lo = QUANTILE_COLUMNS.index("q05")
    hi = QUANTILE_COLUMNS.index("q95")
    median = QUANTILE_COLUMNS.index("q50")
    days = np.unique(origin_day)
    day_index = np.searchsorted(days, origin_day)
    for method, q in reconciled.items():
        remainders = set(summing.remainders)
        for level in sorted(set(summing.levels.values())):
            cols = [summing.nodes.index(n) for n in summing.nodes_at(level) if n not in remainders]
            if not cols:
                continue
            pred = q[:, cols, median]
            act = actual[:, cols]
            ok = np.isfinite(act) & (act > 0) & np.isfinite(pred)
            ape = np.where(ok, np.abs(pred - act) / np.where(ok, act, 1.0), 0.0)
            inside = np.where(ok, (act >= q[:, cols, lo]) & (act <= q[:, cols, hi]), False).astype(float)
            # Day sums pooled over the level's nodes: ape, count, coverage hits.
            sums = np.zeros((len(days), 3))
            np.add.at(sums[:, 0], day_index, ape.sum(axis=1))
            np.add.at(sums[:, 1], day_index, ok.sum(axis=1))
            np.add.at(sums[:, 2], day_index, inside.sum(axis=1))
            value, lower, upper, _ = bootstrap_statistic(
                sums, lambda t: t[:, 0] / t[:, 1], seed, "hierarchy", method, str(level)
            )
            coverage = float(sums[:, 2].sum() / max(sums[:, 1].sum(), 1))
            by_node = {}
            for k, j in enumerate(cols):
                n_ok = ok[:, k].sum()
                by_node[summing.nodes[j]] = float(ape[:, k].sum() / n_ok) if n_ok else float("nan")
            scores.append(
                LevelScore(method, level, len(cols), int(ok.sum()), value, lower, upper, coverage, by_node)
            )
    return scores


def helped_or_hurt(scores: list[LevelScore]) -> list[dict[str, object]]:
    """Per method and level: the change in MAPE against the base, with the paired verdict."""
    base = {s.level: s for s in scores if s.method == "base"}
    out: list[dict[str, object]] = []
    for s in scores:
        if s.method == "base":
            continue
        b = base[s.level]
        change = s.mape - b.mape
        verdict = "helped" if change < -1e-6 else "hurt" if change > 1e-6 else "unchanged"
        out.append(
            {
                "method": s.method,
                "level": s.level,
                "level_name": LEVEL_NAMES.get(s.level, str(s.level)),
                "base_mape": b.mape,
                "mape": s.mape,
                "change": change,
                "verdict": verdict,
            }
        )
    return out


def replicate_count() -> int:
    return POLICY.bootstrap_replicates


__all__ = [
    "run_study",
    "helped_or_hurt",
    "StudyResult",
    "LevelScore",
    "METHODS",
    "LEVEL_NAMES",
    "resample_day_sums",
    "bottom_up",
    "top_down",
    "mint",
]
