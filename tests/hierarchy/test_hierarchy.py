"""The summing matrix matches the table, the three coherence tests, and the reconciliation methods."""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from lookahead_hierarchy.reconcile import bottom_up, historical_proportions, mint, shrink_covariance, top_down
from lookahead_hierarchy.summing import CoherenceError, SummingMatrix, check_coherent


def _table() -> pl.DataFrame:
    rows = [
        ("US48", None, 0),
        ("Eastern", "US48", 1),
        ("Western", "US48", 1),
        ("MIDA", "Eastern", 2),
        ("CAL", "Western", 2),
        ("PJM", "MIDA", 3),
        ("CISO", "CAL", 3),
        ("LDWP", "CAL", 3),
        ("PJM.AE", "PJM", 4),
        ("PJM.PE", "PJM", 4),
        ("PJM.rest", "PJM", 4),
    ]
    return pl.DataFrame(rows, schema=["node", "parent", "level"], orient="row").with_columns(
        pl.lit("x").alias("kind"), pl.col("node").alias("label")
    )


def test_summing_matrix_rows_match_the_table() -> None:
    s = SummingMatrix.from_table(_table())
    assert s.nodes == _table()["node"].to_list()
    assert s.leaves == ["CISO", "LDWP", "PJM.AE", "PJM.PE", "PJM.rest"]
    assert s.matrix.shape == (11, 5)
    assert s.matrix[s.nodes.index("PJM")].tolist() == [0, 0, 1, 1, 1]
    assert s.matrix[s.nodes.index("US48")].tolist() == [1, 1, 1, 1, 1]
    assert s.matrix[s.nodes.index("CAL")].tolist() == [1, 1, 0, 0, 0]
    assert s.nodes_at(3) == ["PJM", "CISO", "LDWP"]


def test_coherence_passes_a_coherent_set_fails_a_violation_and_refuses_nothing() -> None:
    s = SummingMatrix.from_table(_table())
    leaves = np.array([[100.0, 50.0, 30.0, 40.0, 5.0], [110.0, 55.0, 31.0, 41.0, 4.0]])
    coherent = s.aggregate(leaves)
    assert check_coherent(coherent, s) < 1e-9
    violated = coherent.copy()
    violated[0, s.nodes.index("PJM")] += 1.0
    with pytest.raises(CoherenceError, match="not coherent"):
        check_coherent(violated, s)
    with pytest.raises(CoherenceError, match="no forecasts"):
        check_coherent(np.zeros((0, 11)), s)
    with pytest.raises(CoherenceError):
        check_coherent(np.full((2, 11), np.nan), s)


def test_bottom_up_top_down_and_mint_are_coherent_and_a_coherent_base_is_a_fixed_point() -> None:
    s = SummingMatrix.from_table(_table())
    rng = np.random.default_rng(1)
    leaves = rng.uniform(10, 100, size=(50, 5))
    base = s.aggregate(leaves)
    np.testing.assert_allclose(bottom_up(base, s), base)
    proportions = historical_proportions(leaves)
    assert proportions.sum() == pytest.approx(1.0)
    td = top_down(base, s, proportions)
    check_coherent(td, s)
    np.testing.assert_allclose(td[:, 0], base[:, 0])
    covariance = np.diag(rng.uniform(1, 5, size=11))
    reconciled = mint(base, s, covariance)
    np.testing.assert_allclose(reconciled, base, atol=1e-6)
    # An incoherent base is moved onto the coherent subspace.
    noisy = base + rng.normal(0, 2, size=base.shape)
    fixed = mint(noisy, s, covariance)
    check_coherent(fixed, s)
    with pytest.raises(CoherenceError):
        check_coherent(noisy, s)


def test_shrinkage_moves_toward_the_diagonal() -> None:
    rng = np.random.default_rng(2)
    common = rng.normal(size=(300, 1))
    residuals = common + 0.5 * rng.normal(size=(300, 4))
    shrunk, intensity = shrink_covariance(residuals)
    sample = np.cov(residuals.T)
    assert 0.0 <= intensity <= 1.0
    off = ~np.eye(4, dtype=bool)
    assert np.all(np.abs(shrunk[off]) <= np.abs(sample[off]) + 1e-9)
    np.testing.assert_allclose(np.diag(shrunk), np.diag(sample))


@given(st.lists(st.floats(1.0, 1000.0), min_size=5, max_size=5))
@settings(max_examples=30, deadline=None)
def test_reconciling_a_coherent_row_returns_it(values: list[float]) -> None:
    s = SummingMatrix.from_table(_table())
    base = s.aggregate(np.array([values]))
    np.testing.assert_allclose(bottom_up(base, s), base, rtol=1e-12)
    np.testing.assert_allclose(mint(base, s, np.eye(11)), base, rtol=1e-8, atol=1e-8)


def test_summing_matrix_has_one_row_per_node() -> None:
    s = SummingMatrix.from_table(_table())
    assert s.matrix.shape[0] == len(s.nodes) == _table().height
    assert all(s.matrix[i].sum() >= 1 for i in range(len(s.nodes)))
