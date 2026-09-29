"""The summing matrix from the hierarchy table, and the coherence check.

Nodes are ordered as the table lists them; the leaves are the nodes nobody names as a
parent. ``S`` has one row per node and one column per leaf, with a one where the leaf
sits under the node. A forecast for every node is coherent when it equals ``S`` times its
own leaf rows, to the megawatt.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import polars as pl


class CoherenceError(ValueError):
    pass


@dataclass(frozen=True)
class SummingMatrix:
    nodes: list[str]
    leaves: list[str]
    matrix: np.ndarray
    levels: dict[str, int]
    kinds: dict[str, str] = field(default_factory=dict)
    """Node to kind from the table's ``kind`` column when it has one; ``remainder`` marks the
    bookkeeping node that holds an authority's difference from its subregions."""
    parents: dict[str, str | None] = field(default_factory=dict)

    @property
    def leaf_index(self) -> list[int]:
        return [self.nodes.index(leaf) for leaf in self.leaves]

    @property
    def remainders(self) -> list[str]:
        return [n for n in self.nodes if self.kinds.get(n) == "remainder"]

    @property
    def series(self) -> list[str]:
        """The nodes that are forecast as series: every node but the remainders."""
        return [n for n in self.nodes if self.kinds.get(n) != "remainder"]

    def siblings(self, node: str) -> list[str]:
        """The other leaves under the node's parent."""
        parent = self.parents.get(node)
        return [n for n in self.leaves if n != node and self.parents.get(n) == parent]

    @classmethod
    def from_table(cls, hierarchy: pl.DataFrame) -> SummingMatrix:
        if hierarchy.height == 0:
            raise ValueError("the hierarchy table is empty")
        nodes = hierarchy["node"].to_list()
        parents = dict(zip(nodes, hierarchy["parent"].to_list(), strict=True))
        levels = dict(zip(nodes, (int(v) for v in hierarchy["level"].to_list()), strict=True))
        named_as_parent = {p for p in parents.values() if p is not None}
        leaves = [n for n in nodes if n not in named_as_parent]
        matrix = np.zeros((len(nodes), len(leaves)))
        for j, leaf in enumerate(leaves):
            node: str | None = leaf
            while node is not None:
                matrix[nodes.index(node), j] = 1.0
                node = parents[node]
        kinds = (
            dict(zip(nodes, (str(k) for k in hierarchy["kind"].to_list()), strict=True))
            if "kind" in hierarchy.columns
            else {}
        )
        return cls(nodes=nodes, leaves=leaves, matrix=matrix, levels=levels, kinds=kinds, parents=parents)

    def aggregate(self, leaf_values: np.ndarray) -> np.ndarray:
        """Leaf values (rows by leaves) to every node (rows by nodes)."""
        out: np.ndarray = leaf_values @ self.matrix.T
        return out

    def nodes_at(self, level: int) -> list[str]:
        return [n for n in self.nodes if self.levels[n] == level]


def check_coherent(all_nodes: np.ndarray, summing: SummingMatrix, tolerance_mw: float = 1e-6) -> float:
    """Raise unless every node equals the sum of its leaves; returns the largest gap in megawatts."""
    if all_nodes.size == 0:
        raise CoherenceError("no forecasts to check")
    if all_nodes.shape[1] != len(summing.nodes):
        raise CoherenceError(f"expected {len(summing.nodes)} node columns, got {all_nodes.shape[1]}")
    finite = np.all(np.isfinite(all_nodes), axis=1)
    if not finite.any():
        raise CoherenceError("no finite forecast row to check")
    leaves = all_nodes[finite][:, summing.leaf_index]
    rebuilt = summing.aggregate(leaves)
    gap = float(np.max(np.abs(rebuilt - all_nodes[finite])))
    scale = max(float(np.max(np.abs(all_nodes[finite]))), 1.0)
    if gap > tolerance_mw * scale:
        raise CoherenceError(f"forecasts are not coherent: the largest gap is {gap:.6f} MW")
    return gap
