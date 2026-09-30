"""The summing matrix matches the table, the three coherence tests, and the reconciliation methods."""

from __future__ import annotations

from pathlib import Path

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


def test_reconciled_quantiles_stay_coherent_when_levels_cross() -> None:
    """A linear adjustment can cross a node's quantile levels; removing the crossing must not
    break coherence, which is what sorting every node on its own would do."""
    import numpy as np
    from lookahead_hierarchy.reconcile import reconcile_quantiles
    from lookahead_hierarchy.summing import SummingMatrix, check_coherent

    nodes = pl.DataFrame(
        {
            "node": ["TOP", "A", "B"],
            "parent": [None, "TOP", "TOP"],
            "level": [0, 1, 1],
            "kind": ["lower48", "authority", "authority"],
            "label": ["top", "a", "b"],
        }
    )
    summing = SummingMatrix.from_table(nodes)
    rng = np.random.default_rng(0)
    base = np.empty((5, 3, 5))
    for k in range(5):
        base[:, :, k] = rng.uniform(50, 150, size=(5, 3))
    # A covariance that makes MinT move the nodes by different amounts per level.
    covariance = np.diag([4.0, 1.0, 9.0])
    out = reconcile_quantiles(base, summing, "mint", covariance=covariance)
    for k in range(5):
        check_coherent(out[:, :, k], summing)
    assert np.all(np.diff(out, axis=2) >= -1e-9), "levels are monotone at every node"


def test_a_negative_remainder_is_derived_not_fit_and_bottom_up_keeps_the_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One real authority's subregions sum to more than its demand, so its remainder node is
    negative and no ratio model can be fit to it. The study derives the remainder from the parent
    and the siblings, leaves it out of the accuracy tables, and bottom up then reproduces the
    authority's own median exactly."""
    from lookahead_evaluation.recovery import SIM_WINDOWS
    from lookahead_forecast.interface import PanelData
    from lookahead_hierarchy.nodes import build_node_panel, eligible_subregions, node_table
    from lookahead_hierarchy.study import run_study
    from lookahead_sim.grid import GridSpec, simulate

    grid = simulate(GridSpec(subregion_gap=-0.03), 5)
    authorities = sorted(grid.panel["authority"].unique().to_list())
    subs = eligible_subregions(grid.subregions, authorities, SIM_WINDOWS)
    nodes = node_table(grid.hierarchy, authorities, subs)
    node_panel = build_node_panel(grid.panel, grid.subregions, None, nodes, authorities)
    summing = SummingMatrix.from_table(nodes)
    assert summing.remainders, "the simulated grid has remainder nodes"
    rest = summing.remainders[0]
    rest_demand = node_panel.filter(pl.col("authority") == rest)["demand"]
    assert float(rest_demand.median()) < 0, "the remainder is negative by construction"

    data = PanelData.from_frames(node_panel, None, SIM_WINDOWS, "simulated")
    from lookahead_hierarchy.study import CHECKPOINT_ENV

    monkeypatch.setenv(CHECKPOINT_ENV, str(tmp_path))
    study = run_study(data, summing, seed=5)
    assert list(tmp_path.glob("*.scoring.parquet")), "each chunk's rows were checkpointed"
    again = run_study(data, summing, seed=5)  # read back from the checkpoints
    assert [s.mape for s in again.scores] == [s.mape for s in study.scores]
    assert study.coherence_gap_mw["bottom_up"] < 1e-3
    parent = str(summing.parents[rest])
    j_parent = summing.nodes.index(parent)
    median = 2
    np.testing.assert_allclose(
        study.reconciled["bottom_up"][:, j_parent, median],
        study.reconciled["base"][:, j_parent, median],
        atol=1e-6,
    )
    j_rest = summing.nodes.index(rest)
    assert np.allclose(study.reconciled["base"][:, j_rest, 0], study.reconciled["base"][:, j_rest, 4])
    for score in study.scores:
        assert rest not in score.mape_by_node
        if score.level == summing.levels[rest]:
            assert score.nodes == len(
                [n for n in summing.nodes_at(score.level) if n not in summing.remainders]
            )
