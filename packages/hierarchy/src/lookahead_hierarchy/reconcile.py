"""Three reconciliation methods on the summing matrix.

Bottom up keeps the leaves and rebuilds every aggregate. Top down keeps the top node and
splits it by historical proportions. MinT (minimum trace) finds the coherent set closest to
every base forecast, weighted by the inverse of the base errors' covariance, estimated on
the validation year with the Schafer and Strimmer shrinkage toward its diagonal. Each method
returns a matrix of every node's reconciled value and is checked for coherence to the
megawatt before it is scored.
"""

from __future__ import annotations

import numpy as np

from lookahead_hierarchy.summing import SummingMatrix, check_coherent


def bottom_up(base: np.ndarray, summing: SummingMatrix) -> np.ndarray:
    """``base`` is rows by nodes; only the leaf columns are used."""
    leaves = base[:, summing.leaf_index]
    out = summing.aggregate(leaves)
    check_coherent(out, summing)
    return out


def historical_proportions(actual_leaves: np.ndarray) -> np.ndarray:
    """Each leaf's average share of the total over the rows given (the validation year)."""
    finite = np.all(np.isfinite(actual_leaves), axis=1)
    totals = actual_leaves[finite].sum(axis=1, keepdims=True)
    ok = totals[:, 0] > 0
    shares = actual_leaves[finite][ok] / totals[ok]
    out: np.ndarray = shares.mean(axis=0)
    return out


def top_down(base: np.ndarray, summing: SummingMatrix, proportions: np.ndarray) -> np.ndarray:
    """``base`` rows by nodes; the first node has to be the top of the hierarchy."""
    if abs(proportions.sum() - 1.0) > 1e-9:
        raise ValueError("proportions have to sum to one")
    top = base[:, 0:1]
    leaves = top * proportions[None, :]
    out = summing.aggregate(leaves)
    check_coherent(out, summing)
    return out


def shrink_covariance(residuals: np.ndarray) -> tuple[np.ndarray, float]:
    """Schafer and Strimmer shrinkage of the sample covariance toward its diagonal.

    ``residuals`` is rows by nodes (base forecast errors on the validation year). Returns the
    shrunk covariance and the shrinkage intensity."""
    finite = np.all(np.isfinite(residuals), axis=1)
    r = residuals[finite]
    n, p = r.shape
    if n < 2:
        raise ValueError("at least two residual rows are needed")
    centred = r - r.mean(axis=0)
    cov = centred.T @ centred / (n - 1)
    sd = np.sqrt(np.diag(cov))
    sd[sd == 0] = 1.0
    corr = cov / np.outer(sd, sd)
    z = centred / sd
    # Variance of the sample correlations, the numerator of the optimal intensity. With w_nij =
    # z_ni z_nj, sum_n (w_nij - mean_ij)^2 = sum_n w_nij^2 - n mean_ij^2, and both sums are
    # matrix products, so the rows by nodes by nodes tensor (three gigabytes on the real
    # hierarchy) is never formed.
    products = z.T @ z
    squares = (z**2).T @ (z**2)
    w_mean = products / n
    var = (squares - n * w_mean**2) * n / ((n - 1) ** 3)
    off = ~np.eye(p, dtype=bool)
    numerator = var[off].sum()
    denominator = (corr[off] ** 2).sum()
    intensity = float(np.clip(numerator / denominator if denominator > 0 else 1.0, 0.0, 1.0))
    shrunk_corr = (1 - intensity) * corr + intensity * np.eye(p)
    return shrunk_corr * np.outer(sd, sd), intensity


def mint(base: np.ndarray, summing: SummingMatrix, covariance: np.ndarray) -> np.ndarray:
    """Minimum trace reconciliation: S (S' W^-1 S)^-1 S' W^-1 y_hat, rows by nodes."""
    s = summing.matrix
    w_inv = np.linalg.pinv(covariance)
    middle = np.linalg.pinv(s.T @ w_inv @ s)
    projector = s @ middle @ s.T @ w_inv
    out: np.ndarray = base @ projector.T
    check_coherent(out, summing)
    return out


def reconcile_quantiles(
    quantiles: np.ndarray, summing: SummingMatrix, method: str, **kwargs: object
) -> np.ndarray:
    """Apply a linear method to every quantile column: ``quantiles`` is rows by nodes by levels.

    Quantile crossing after a linear adjustment is removed at the leaves, by sorting each leaf's
    levels, and the upper nodes are rebuilt from the sorted leaves: a sum of ascending sequences
    is ascending, so the result is both coherent and monotone in the level. Sorting every node
    on its own would break coherence wherever the crossing differs between a node and its leaves.
    """
    out = np.empty_like(quantiles)
    for k in range(quantiles.shape[2]):
        if method == "bottom_up":
            out[:, :, k] = bottom_up(quantiles[:, :, k], summing)
        elif method == "top_down":
            out[:, :, k] = top_down(quantiles[:, :, k], summing, kwargs["proportions"])  # type: ignore[arg-type]
        elif method == "mint":
            out[:, :, k] = mint(quantiles[:, :, k], summing, kwargs["covariance"])  # type: ignore[arg-type]
        else:
            raise KeyError(method)
    leaves = np.sort(out[:, summing.leaf_index, :], axis=2)
    rebuilt = np.empty_like(out)
    for k in range(quantiles.shape[2]):
        rebuilt[:, :, k] = summing.aggregate(leaves[:, :, k])
    return rebuilt
