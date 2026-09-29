"""Seeded randomness that does not depend on the order rows arrive in.

Every seeded sample, shuffle, split or permutation in this repository sorts its
input by a stated key first, so the same seed gives the same draw whatever order
a query returned the rows in. Day 9 of the series found two published estimates
that moved between runs for want of this.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import polars as pl


def rng(seed: int, *stream: int | str) -> np.random.Generator:
    """A generator for a named stream, so two steps sharing a seed do not share draws."""
    seq = np.random.SeedSequence([seed, *[_to_int(s) for s in stream]])
    return np.random.default_rng(seq)


def _to_int(value: int | str) -> int:
    if isinstance(value, int):
        return value
    return int.from_bytes(value.encode("utf-8")[:8].ljust(8, b"\0"), "little") % (2**31)


def sorted_frame(frame: pl.DataFrame, keys: Sequence[str]) -> pl.DataFrame:
    missing = [k for k in keys if k not in frame.columns]
    if missing:
        raise KeyError(f"cannot sort on absent columns {missing}")
    return frame.sort(list(keys), maintain_order=False)


def seeded_split(
    frame: pl.DataFrame, key: str, seed: int, shares: Sequence[float], names: Sequence[str]
) -> pl.DataFrame:
    """Assign each row a split name by a seeded draw taken in sorted key order."""
    if abs(sum(shares) - 1.0) > 1e-9:
        raise ValueError("split shares must sum to one")
    if len(shares) != len(names):
        raise ValueError("one name per share")
    ordered = sorted_frame(frame, [key])
    draws = rng(seed, "split", key).random(ordered.height)
    edges = np.cumsum(shares)
    idx = np.searchsorted(edges, draws, side="right")
    idx = np.clip(idx, 0, len(names) - 1)
    labels = np.asarray(names, dtype=object)[idx]
    return ordered.with_columns(pl.Series("split", labels.astype(str)))


def seeded_permutation(n: int, seed: int, *stream: int | str) -> np.ndarray:
    return rng(seed, "permutation", *stream).permutation(n)
