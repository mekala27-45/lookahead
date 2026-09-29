"""Stage: skill against the operator, the cross check table, and the headline numbers.

Reads the scoring frames of every backend that has run (own, gbm, the seasonal naive), keeps
the authorities whose operator forecast is comparable (data/eia930/authorities.csv), and
publishes for each backend the skill table in three horizon bands with wins, losses and
ties after Benjamini-Hochberg, the cross check table where every model sits beside the
seasonal naive and the operator, and the two headline numbers with intervals. The
authorities whose operator is not comparable are listed with the reason and never counted.
Writes results/skill/*.parquet and results/manifests/skill.json.
"""

from __future__ import annotations

import numpy as np
import polars as pl

from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths
from lookahead_evaluation.metrics import (
    day_sums,
    row_errors,
    stat_mape,
    stat_mape_naive,
    stat_mape_operator,
    sums_matrix,
)
from lookahead_evaluation.skill import BANDS, SkillRow, headline, headline_interval, skill_table

BAND_LABELS = {"h1_24": "horizons 1 to 24", "h25_48": "horizons 25 to 48", "target_day": "the target day"}


def run(paths: Paths, as_of: str, seed: int) -> Manifest:
    authorities = pl.read_csv(paths.eia / "authorities.csv")
    comparable = authorities.filter(pl.col("backtest_eligible") & pl.col("operator_comparable"))[
        "authority"
    ].to_list()
    not_comparable = authorities.filter(pl.col("backtest_eligible") & ~pl.col("operator_comparable"))
    folder = paths.results / "skill"
    folder.mkdir(parents=True, exist_ok=True)
    manifest = Manifest(as_of=as_of, seed=seed)
    scorings: dict[str, pl.DataFrame] = {}
    for backend in ("own", "gbm", "seasonal_naive"):
        path = paths.results / "backtest" / backend / "scoring.parquet"
        if path.exists():
            scorings[backend] = pl.read_parquet(path)
    if not scorings:
        raise FileNotFoundError("no backtest scoring found under results/backtest")
    all_rows: list[dict[str, object]] = []
    for backend, scoring in scorings.items():
        model = backend if backend in ("own", "gbm", "seasonal_naive") else "none"
        w = Scribe(
            manifest,
            source="real:eia930",
            model=model,
            population=f"{len(comparable)} authorities with a comparable operator forecast, test year",
            origin="lookahead_registry.stages.skill",
        )
        sub = scoring.filter(pl.col("authority").is_in(comparable))
        for band in BANDS:
            rows = skill_table(sub, seed, band)
            counts = headline(rows)
            intervals = headline_interval(rows, seed)
            prefix = f"skill.{backend}.{band}"
            w.put(f"{prefix}.wins", counts["wins"], "int")
            w.put(f"{prefix}.losses", counts["losses"], "int")
            w.put(f"{prefix}.ties", counts["ties"], "int")
            w.put(f"{prefix}.authorities", counts["authorities"], "int")
            w.put(f"{prefix}.wins_lower", intervals["wins"][0], "int")
            w.put(f"{prefix}.wins_upper", intervals["wins"][1], "int")
            w.put(f"{prefix}.losses_lower", intervals["losses"][0], "int")
            w.put(f"{prefix}.losses_upper", intervals["losses"][1], "int")
            pooled = _pooled_skill(rows)
            w.put(f"{prefix}.model_mape_pooled", pooled[0], "pct2")
            w.put(f"{prefix}.operator_mape_pooled", pooled[1], "pct2")
            w.put(f"{prefix}.skill_pooled", pooled[2], "spct1")
            w.put(
                f"{prefix}.median_skill",
                float(np.median([r.skill for r in rows])) if rows else 0.0,
                "spct1",
            )
            w.table(
                f"{prefix}.table",
                [
                    "Authority",
                    "Hours",
                    "Model MAPE",
                    "Operator MAPE",
                    "Skill",
                    "lower",
                    "upper",
                    "p value",
                    "Verdict",
                ],
                ["text", "int", "pct2", "pct2", "spct1", "spct1", "spct1", "float3", "text"],
                [
                    [
                        r.authority,
                        r.hours,
                        r.model_mape,
                        r.operator_mape,
                        r.skill,
                        r.skill_lower,
                        r.skill_upper,
                        r.p_value,
                        r.verdict,
                    ]
                    for r in rows
                ],
            )
            for r in rows:
                all_rows.append({"backend": backend, "band": band, **r.__dict__})
        _by_authority_verdicts(
            w, backend, [r for r in all_rows if r["backend"] == backend and r["band"] == "h1_24"]
        )
    pl.DataFrame(all_rows).write_parquet(folder / "skill_rows.parquet")

    w = Scribe(
        manifest,
        source="real:eia930",
        model="both",
        population="authorities in the backtest, test year",
        origin="lookahead_registry.stages.skill",
    )
    w.put("skill.comparable_authorities", len(comparable), "int")
    w.put("skill.not_comparable_authorities", not_comparable.height, "int")
    w.put(
        "skill.not_comparable_list",
        ", ".join(
            f"{r['authority']} (forecast to demand {r['operator_median_ratio']:.2f} validation, {r['operator_median_ratio_test']:.2f} test)"
            for r in not_comparable.sort("authority").iter_rows(named=True)
        )
        or "none",
        "text",
    )
    w.table(
        "skill.not_comparable",
        ["Authority", "Validation median ratio", "Test median ratio", "Why"],
        ["text", "float2", "float2", "text"],
        [
            [
                r["authority"],
                r["operator_median_ratio"],
                r["operator_median_ratio_test"],
                "the published forecast covers a different scope than the demand series",
            ]
            for r in not_comparable.sort("authority").iter_rows(named=True)
        ]
        or [["none", None, None, "every operator is comparable"]],
    )
    _crosscheck(w, scorings, comparable)
    manifest.save(paths.results / "manifests" / "skill.json")
    return manifest


def _pooled_skill(rows: list[SkillRow]) -> tuple[float, float, float]:
    hours = sum(r.hours for r in rows) or 1
    model = sum(r.model_mape * r.hours for r in rows) / hours
    operator = sum(r.operator_mape * r.hours for r in rows) / hours
    return model, operator, 1.0 - model / operator if operator else 0.0


def _by_authority_verdicts(w: Scribe, backend: str, rows: list[dict[str, object]]) -> None:
    for r in rows:
        w.put(f"skill.{backend}.verdict.{r['authority']}", str(r["verdict"]), "text")
        w.put(f"skill.{backend}.value.{r['authority']}", float(str(r["skill"])), "spct1")


def _crosscheck(w: Scribe, scorings: dict[str, pl.DataFrame], comparable: list[str]) -> None:
    """own against gbm on the same rows, the seasonal naive and the operator beside them."""
    per: dict[str, dict[str, tuple[float, float, float]]] = {}
    for backend, scoring in scorings.items():
        errors = row_errors(scoring.filter(pl.col("authority").is_in(comparable) & (pl.col("horizon") <= 24)))
        for authority in sorted(errors["authority"].unique().to_list()):
            totals = sums_matrix(day_sums(errors.filter(pl.col("authority") == authority))).sum(
                axis=0, keepdims=True
            )
            per.setdefault(authority, {})[backend] = (
                float(stat_mape(totals)[0]),
                float(stat_mape_operator(totals)[0]),
                float(stat_mape_naive(totals)[0]),
            )
    rows: list[list[Scalar]] = []
    disagreements = 0
    for authority, values in sorted(per.items()):
        own = values.get("own", (float("nan"),) * 3)[0]
        gbm = values.get("gbm", (float("nan"),) * 3)[0]
        any_backend = next(iter(values.values()))
        operator, naive = any_backend[1], any_backend[2]
        better = "own" if own < gbm else "gbm" if gbm < own else "tie"
        # The two backends disagree when they fall on different sides of the operator.
        disagree = (own < operator) != (gbm < operator) if own == own and gbm == gbm else False
        disagreements += int(disagree)
        rows.append([authority, own, gbm, naive, operator, better, "yes" if disagree else "no"])
    w.table(
        "skill.crosscheck",
        [
            "Authority",
            "own MAPE",
            "gbm MAPE",
            "Seasonal naive MAPE",
            "Operator MAPE",
            "Lower error",
            "Disagree on the operator",
        ],
        ["text", "pct2", "pct2", "pct2", "pct2", "text", "text"],
        rows,
    )
    w.put("skill.crosscheck.disagreements", disagreements, "int")
    w.put("skill.crosscheck.authorities", len(rows), "int")
    own_better = sum(1 for r in rows if r[5] == "own")
    w.put("skill.crosscheck.own_better", own_better, "int")
    w.put("skill.crosscheck.gbm_better", sum(1 for r in rows if r[5] == "gbm"), "int")
