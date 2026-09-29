"""Skill against the operator: the headline of the build, with wins, losses and ties.

For each authority, over the rows where the operator published a forecast: the model's MAPE
and the operator's on the same target hours, the skill score (one minus their ratio), a
paired block bootstrap interval over test days, and a block sign flip p value for the
daily paired difference. Benjamini-Hochberg across the authorities decides the wins and
losses; everything else is a tie. Three horizon bands are reported: 1 to 24 (the headline,
where the model's origin is later than the operator's issue and the timing favours the
model), 25 to 48 (where the operator issued later than the model), and the target day.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl
from lookahead_core.config import POLICY

from lookahead_evaluation.bootstrap import benjamini_hochberg, block_sign_flip_pvalue, bootstrap_statistic
from lookahead_evaluation.metrics import (
    column,
    day_sums,
    row_errors,
    stat_mape_operator,
    stat_skill,
    sums_matrix,
)


@dataclass(frozen=True)
class SkillRow:
    authority: str
    band: str
    hours: int
    model_mape: float
    operator_mape: float
    skill: float
    skill_lower: float
    skill_upper: float
    p_value: float
    verdict: str


BANDS = {
    "h1_24": pl.col("horizon") <= 24,
    "h25_48": pl.col("horizon") > 24,
    "target_day": pl.col("local_day") == pl.col("target_day"),
}


def skill_table(scoring: pl.DataFrame, seed: int, band: str = "h1_24") -> list[SkillRow]:
    errors = row_errors(scoring).filter(BANDS[band]).filter(pl.col("has_operator") == 1.0)
    rows: list[SkillRow] = []
    pvalues: list[float] = []
    for authority in sorted(errors["authority"].unique().to_list()):
        e = errors.filter(pl.col("authority") == authority)
        days = day_sums(e)
        sums = sums_matrix(days)
        skill, lower, upper, _ = bootstrap_statistic(sums, stat_skill, seed, "skill", band, authority)
        operator = float(stat_mape_operator(sums.sum(axis=0, keepdims=True))[0])
        model = float(sums[:, column("ape_model_paired")].sum() / sums[:, column("n_operator")].sum())
        daily_diff = (
            sums[:, column("ape_model_paired")] - sums[:, column("ape_operator_paired")]
        ) / np.maximum(sums[:, column("n_operator")], 1)
        p = block_sign_flip_pvalue(
            daily_diff,
            POLICY.bootstrap_block_days,
            POLICY.bootstrap_replicates,
            seed,
            "skill_p",
            band,
            authority,
        )
        rows.append(
            SkillRow(
                authority,
                band,
                int(sums[:, column("n_operator")].sum()),
                model,
                operator,
                skill,
                lower,
                upper,
                p,
                "tie",
            )
        )
        pvalues.append(p)
    rejected = benjamini_hochberg(np.asarray(pvalues), POLICY.bh_q)
    out: list[SkillRow] = []
    for row, reject in zip(rows, rejected, strict=True):
        verdict = "tie"
        if reject and row.skill > 0:
            verdict = "win"
        elif reject and row.skill < 0:
            verdict = "loss"
        out.append(
            SkillRow(
                row.authority,
                row.band,
                row.hours,
                row.model_mape,
                row.operator_mape,
                row.skill,
                row.skill_lower,
                row.skill_upper,
                row.p_value,
                verdict,
            )
        )
    return out


def headline(rows: list[SkillRow]) -> dict[str, int]:
    return {
        "wins": sum(r.verdict == "win" for r in rows),
        "losses": sum(r.verdict == "loss" for r in rows),
        "ties": sum(r.verdict == "tie" for r in rows),
        "authorities": len(rows),
    }


def headline_interval(
    rows: list[SkillRow], seed: int, replicates: int = POLICY.bootstrap_replicates
) -> dict[str, tuple[float, float]]:
    """Intervals on the win and loss counts: a bootstrap over authorities, resampling the
    per authority verdicts. It answers how stable the counts are under a different draw of
    authorities, which is the reader's question when comparing two builds."""
    from lookahead_core.seeds import rng

    if not rows:
        return {"wins": (0.0, 0.0), "losses": (0.0, 0.0)}
    g = rng(seed, "headline")
    wins = np.asarray([r.verdict == "win" for r in rows], dtype=float)
    losses = np.asarray([r.verdict == "loss" for r in rows], dtype=float)
    n = len(rows)
    idx = g.integers(0, n, size=(replicates, n))
    w = wins[idx].sum(axis=1)
    lo = losses[idx].sum(axis=1)
    alpha = (1 - POLICY.interval_level) / 2
    return {
        "wins": (float(np.quantile(w, alpha)), float(np.quantile(w, 1 - alpha))),
        "losses": (float(np.quantile(lo, alpha)), float(np.quantile(lo, 1 - alpha))),
    }
