"""Block bootstrap over test days, the block sign flip test, and Benjamini-Hochberg.

Every interval in this build is a moving block bootstrap over days: a metric is a ratio of
sums over rows, each day contributes its sums, and a replicate is a resample of whole
blocks of consecutive days. Blocks keep the week's autocorrelation inside the resample;
a plain row bootstrap would call a week of hot weather 168 independent draws.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from lookahead_core.config import POLICY
from lookahead_core.seeds import rng


def resample_day_sums(
    sums: np.ndarray, block_days: int, replicates: int, seed: int, *stream: int | str
) -> np.ndarray:
    """``sums`` is days by statistics, in day order. Returns replicates by statistics: the sums of a
    moving block resample of the days for each replicate."""
    days = sums.shape[0]
    if days == 0:
        raise ValueError("no days to resample")
    block = max(1, min(block_days, days))
    blocks_needed = int(np.ceil(days / block))
    g = rng(seed, "block_bootstrap", *stream)
    starts = g.integers(0, days - block + 1, size=(replicates, blocks_needed))
    # Prefix sums make a block's total a difference of two rows.
    prefix = np.concatenate([np.zeros((1, sums.shape[1])), np.cumsum(sums, axis=0)], axis=0)
    totals = np.zeros((replicates, sums.shape[1]))
    for j in range(blocks_needed):
        s = starts[:, j]
        totals += prefix[s + block] - prefix[s]
    # The last block may overshoot the day count; the overshoot is trimmed in expectation by
    # scaling to the day count, which keeps ratios of sums unbiased.
    totals *= days / (blocks_needed * block)
    return totals


def interval(values: np.ndarray, level: float = POLICY.interval_level) -> tuple[float, float]:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return (float("nan"), float("nan"))
    alpha = (1.0 - level) / 2.0
    return (float(np.quantile(finite, alpha)), float(np.quantile(finite, 1.0 - alpha)))


def bootstrap_statistic(
    sums: np.ndarray,
    statistic: Callable[[np.ndarray], np.ndarray],
    seed: int,
    *stream: int | str,
    block_days: int = POLICY.bootstrap_block_days,
    replicates: int = POLICY.bootstrap_replicates,
) -> tuple[float, float, float, int]:
    """The statistic on the full sample and its interval; ``statistic`` maps (replicates, K) sums to (replicates,)."""
    point = float(statistic(sums.sum(axis=0, keepdims=True))[0])
    totals = resample_day_sums(sums, block_days, replicates, seed, *stream)
    draws = statistic(totals)
    lower, upper = interval(draws)
    return point, lower, upper, replicates


def block_sign_flip_pvalue(
    daily: np.ndarray, block_days: int, replicates: int, seed: int, *stream: int | str
) -> float:
    """Two sided p value that the mean of ``daily`` is zero, flipping the sign of whole blocks.

    Under the null the paired differences are symmetric about zero and exchangeable in
    blocks; flipping each block's sign at random gives the null distribution of the mean."""
    daily = daily[np.isfinite(daily)]
    if len(daily) < 2:
        return 1.0
    block = max(1, min(block_days, len(daily)))
    blocks = int(np.ceil(len(daily) / block))
    padded = np.concatenate([daily, np.zeros(blocks * block - len(daily))]).reshape(blocks, block)
    block_sums = padded.sum(axis=1)
    observed = abs(daily.mean())
    g = rng(seed, "sign_flip", *stream)
    signs = g.choice([-1.0, 1.0], size=(replicates, blocks))
    null = np.abs((signs * block_sums).sum(axis=1)) / len(daily)
    return float((np.sum(null >= observed - 1e-15) + 1) / (replicates + 1))


def benjamini_hochberg(pvalues: np.ndarray, q: float = POLICY.bh_q) -> np.ndarray:
    """Which hypotheses are rejected at false discovery rate q."""
    p = np.asarray(pvalues, dtype=np.float64)
    m = len(p)
    if m == 0:
        return np.zeros(0, dtype=bool)
    order = np.argsort(p)
    ranked = p[order]
    thresholds = q * (np.arange(1, m + 1) / m)
    below = ranked <= thresholds
    rejected = np.zeros(m, dtype=bool)
    if below.any():
        k = int(np.max(np.flatnonzero(below)))
        rejected[order[: k + 1]] = True
    return rejected
