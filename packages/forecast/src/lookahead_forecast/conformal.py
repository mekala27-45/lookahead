"""Split conformal quantiles per horizon bucket.

Two flavours. ``RelativeConformal`` turns a point forecast into quantiles: the residual as a
share of the forecast, ``(y - f) / f``, has its empirical quantiles taken on the validation
year within buckets of horizon hours, and each served level adds its quantile to the point
forecast. ``IntervalConformal`` adjusts a backend's own quantile forecasts (conformalized
quantile regression): for each interval the score ``max(lower - y, y - upper) / f`` is
measured on validation and its ``(1 - alpha)(1 + 1/n)`` quantile widens or narrows the
interval on test. Both are calibrated once, before the test year, and frozen.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def bucket_of(horizons: np.ndarray, bucket_hours: int) -> np.ndarray:
    return (horizons - 1) // bucket_hours


@dataclass(frozen=True)
class RelativeConformal:
    levels: tuple[float, ...]
    bucket_hours: int
    offsets: np.ndarray
    """Buckets by levels: the relative residual quantile to add at each level."""
    calibration_rows: int

    def apply(self, point: np.ndarray, horizons: np.ndarray) -> np.ndarray:
        """Point ratios (rows) to quantile ratios (rows by levels)."""
        b = bucket_of(horizons, self.bucket_hours)
        b = np.clip(b, 0, self.offsets.shape[0] - 1)
        out: np.ndarray = point[:, None] * (1.0 + self.offsets[b])
        return out


def calibrate_relative(
    pred: np.ndarray, actual: np.ndarray, horizons: np.ndarray, levels: tuple[float, ...], bucket_hours: int
) -> RelativeConformal:
    ok = np.isfinite(pred) & np.isfinite(actual) & (pred > 0)
    if ok.sum() < 100:
        raise ValueError(f"conformal calibration needs at least 100 rows, got {int(ok.sum())}")
    rel = (actual[ok] - pred[ok]) / pred[ok]
    b = bucket_of(horizons[ok], bucket_hours)
    buckets = int(b.max()) + 1
    offsets = np.zeros((buckets, len(levels)))
    for k in range(buckets):
        r = rel[b == k]
        if len(r) < 20:
            r = rel
        n = len(r)
        for j, q in enumerate(levels):
            # The finite sample correction from split conformal: the ceil((n + 1) q) order statistic.
            rank = min(max(int(np.ceil((n + 1) * q)), 1), n)
            offsets[k, j] = np.sort(r)[rank - 1] if q != 0.5 else np.median(r)
    # The median offset is zero by construction: the point forecast is the median.
    median_index = [i for i, q in enumerate(levels) if abs(q - 0.5) < 1e-9]
    for i in median_index:
        offsets[:, i] = 0.0
    return RelativeConformal(
        levels=levels, bucket_hours=bucket_hours, offsets=offsets, calibration_rows=int(ok.sum())
    )


@dataclass(frozen=True)
class IntervalConformal:
    levels: tuple[float, ...]
    bucket_hours: int
    widening: np.ndarray
    """Buckets by intervals: the relative widening of each symmetric interval, lowest level first."""
    calibration_rows: int

    def apply(self, quantiles: np.ndarray, horizons: np.ndarray) -> np.ndarray:
        """Quantile ratios (rows by levels) adjusted so the validation coverage holds."""
        out = quantiles.copy()
        b = np.clip(bucket_of(horizons, self.bucket_hours), 0, self.widening.shape[0] - 1)
        pairs = _pairs(self.levels)
        centre = quantiles[:, _median_index(self.levels)]
        for p, (lo, hi) in enumerate(pairs):
            w = self.widening[b, p] * np.abs(centre)
            out[:, lo] = quantiles[:, lo] - w
            out[:, hi] = quantiles[:, hi] + w
        return out


def _median_index(levels: tuple[float, ...]) -> int:
    return min(range(len(levels)), key=lambda i: abs(levels[i] - 0.5))


def _pairs(levels: tuple[float, ...]) -> list[tuple[int, int]]:
    """Symmetric level pairs, (0.05, 0.95) and (0.25, 0.75) for the five served levels."""
    pairs = []
    for i, q in enumerate(levels):
        if q < 0.5:
            j = min(range(len(levels)), key=lambda k: abs(levels[k] - (1 - q)))
            pairs.append((i, j))
    return pairs


def calibrate_interval(
    quantiles: np.ndarray,
    actual: np.ndarray,
    horizons: np.ndarray,
    levels: tuple[float, ...],
    bucket_hours: int,
) -> IntervalConformal:
    centre = quantiles[:, _median_index(levels)]
    ok = np.isfinite(actual) & np.isfinite(centre) & (centre > 0) & np.all(np.isfinite(quantiles), axis=1)
    if ok.sum() < 100:
        raise ValueError(f"interval calibration needs at least 100 rows, got {int(ok.sum())}")
    b = bucket_of(horizons[ok], bucket_hours)
    buckets = int(b.max()) + 1
    pairs = _pairs(levels)
    widening = np.zeros((buckets, len(pairs)))
    for p, (lo, hi) in enumerate(pairs):
        alpha = 2 * levels[lo]
        score = np.maximum(quantiles[ok, lo] - actual[ok], actual[ok] - quantiles[ok, hi]) / np.abs(
            centre[ok]
        )
        for k in range(buckets):
            s = score[b == k]
            if len(s) < 20:
                s = score
            n = len(s)
            rank = min(max(int(np.ceil((n + 1) * (1 - alpha))), 1), n)
            widening[k, p] = np.sort(s)[rank - 1]
    return IntervalConformal(
        levels=levels, bucket_hours=bucket_hours, widening=widening, calibration_rows=int(ok.sum())
    )
