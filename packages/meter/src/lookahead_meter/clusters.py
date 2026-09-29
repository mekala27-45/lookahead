"""Load shape clusters: each household's mean weekday and weekend daily profile at half hour
resolution, normalized by its mean, clustered by k-means with the number of clusters chosen by
the silhouette score on a validation half of the households and the choice recorded."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl
from lookahead_core.config import POLICY

SLOTS = 48
EVENING_SLOTS = tuple(range(34, 40))
"""17:00 to 19:30, the evening peak."""
MORNING_SLOTS = tuple(range(12, 20))
"""06:00 to 09:30."""
NIGHT_SLOTS = tuple(range(0, 12))
"""00:00 to 05:30."""


@dataclass
class Clustering:
    k: int
    silhouette_by_k: dict[int, float]
    centroids: np.ndarray
    """k by 96: weekday slots then weekend slots, as ratios to the household mean."""
    assignment: pl.DataFrame
    """household, tariff, cluster, mean_kwh."""
    labels: dict[int, str] = field(default_factory=dict)
    households: int = 0
    validation_households: int = 0


def profile_matrix(profiles: pl.DataFrame, min_days: int = 180) -> tuple[list[str], np.ndarray, pl.DataFrame]:
    """Households with at least min_days of readings and every slot present; returns the sorted
    identifiers, the 96 column matrix of ratios to the household mean, and the household table."""
    kept = profiles.filter((pl.col("days") >= min_days) & (pl.col("mean_kwh") > 0))
    wide = (
        kept.with_columns(
            (pl.col("daytype") + "_" + pl.col("slot").cast(pl.Utf8).str.zfill(2)).alias("key"),
            (pl.col("kwh") / pl.col("mean_kwh")).alias("ratio"),
        )
        .pivot(
            on="key", index=["household", "tariff", "mean_kwh"], values="ratio", aggregate_function="first"
        )
        .sort("household")
    )
    columns = [f"{d}_{s:02d}" for d in ("weekday", "weekend") for s in range(SLOTS)]
    missing = [c for c in columns if c not in wide.columns]
    for c in missing:
        wide = wide.with_columns(pl.lit(None, dtype=pl.Float64).alias(c))
    wide = wide.drop_nulls(subset=columns)
    x = wide.select(columns).to_numpy().astype(np.float64)
    return wide["household"].to_list(), x, wide.select("household", "tariff", "mean_kwh")


def choose_and_fit(
    x: np.ndarray, seed: int, candidates: tuple[int, ...] = POLICY.meter_cluster_range
) -> tuple[int, dict[int, float], np.ndarray, np.ndarray]:
    """Fit on the even rows, score the silhouette of the odd rows assigned to the nearest
    centroid, keep the k with the best validation silhouette, then fit on every row."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score

    fit_rows = x[0::2]
    valid_rows = x[1::2]
    scores: dict[int, float] = {}
    for k in candidates:
        model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(fit_rows)
        labels = model.predict(valid_rows)
        if len(set(labels.tolist())) < 2:
            scores[k] = -1.0
            continue
        scores[k] = float(silhouette_score(valid_rows, labels, random_state=seed))
    best = max(candidates, key=lambda k: (scores[k], -k))
    final = KMeans(n_clusters=best, n_init=10, random_state=seed).fit(x)
    order = np.argsort(-final.cluster_centers_[:, list(EVENING_SLOTS)].mean(axis=1), kind="stable")
    # Clusters are numbered by their evening share, largest first, so the numbering is stable.
    centroids = final.cluster_centers_[order]
    remap = {int(old): new for new, old in enumerate(order)}
    labels_all = np.array([remap[int(label)] for label in final.labels_])
    return best, scores, centroids, labels_all


def describe(centroid: np.ndarray) -> str:
    """A shape word from the weekday profile: evening peak, morning peak, double peak, flat, night heavy."""
    weekday = centroid[:SLOTS]
    evening = weekday[list(EVENING_SLOTS)].mean()
    morning = weekday[list(MORNING_SLOTS)].mean()
    night = weekday[list(NIGHT_SLOTS)].mean()
    spread = weekday.max() / max(weekday.min(), 1e-9)
    if spread < 1.6:
        return "flat"
    if night > 1.0 and night >= evening:
        return "night heavy"
    if morning > 1.05 and evening > 1.05 and abs(morning - evening) < 0.15:
        return "double peak"
    if morning > evening:
        return "morning peak"
    return "evening peak"


def cluster_households(profiles: pl.DataFrame, seed: int) -> Clustering:
    households, x, table = profile_matrix(profiles)
    if len(households) < 50:
        raise ValueError(f"only {len(households)} households have a full profile; the clustering needs more")
    k, scores, centroids, labels = choose_and_fit(x, seed)
    assignment = table.with_columns(pl.Series("cluster", labels.astype(np.int64)))
    described = {c: describe(centroids[c]) for c in range(k)}
    return Clustering(
        k=k,
        silhouette_by_k=scores,
        centroids=centroids,
        assignment=assignment,
        labels=described,
        households=len(households),
        validation_households=len(x[1::2]),
    )


def peak_shares(profiles: pl.DataFrame, assignment: pl.DataFrame) -> pl.DataFrame:
    """Each cluster's households, mean kWh, and share of the panel's weekday evening peak."""
    weekday = profiles.filter((pl.col("daytype") == "weekday") & pl.col("slot").is_in(list(EVENING_SLOTS)))
    joined = weekday.join(assignment.select("household", "cluster"), on="household", how="inner")
    by_cluster = joined.group_by("cluster").agg(
        pl.col("household").n_unique().alias("households"),
        pl.col("kwh").sum().alias("evening_kwh"),
    )
    total = float(by_cluster["evening_kwh"].sum())
    means = assignment.group_by("cluster").agg(pl.col("mean_kwh").mean().alias("mean_kwh"))
    return (
        by_cluster.join(means, on="cluster", how="left")
        .with_columns((pl.col("evening_kwh") / total).alias("evening_peak_share"))
        .sort("cluster")
    )
