"""The registry gates: a candidate backend serves only if it clears every one.

Each gate is a pure function of what the pipeline measured, so a test can hand it a clean
input, a deliberate violation and an empty input. The seven gates: MAPE at horizons 1 to 24
no worse than the seasonal naive in every authority; skill against the operator not
significantly negative in more than the stated share of authorities after correction; 90
percent coverage on validation inside the stated band; the median peak timing error at or
below the stated hours; coherence after reconciliation exact; p99 latency of issuing a forecast
at or below the ceiling; the leakage check green.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lookahead_core.config import POLICY

GATE_NAMES: tuple[str, ...] = (
    "mape_not_worse_than_naive",
    "skill_not_significantly_negative",
    "coverage_90_on_validation",
    "peak_timing_median",
    "coherence_exact",
    "p99_latency",
    "leakage_check_green",
)


class GateInputError(ValueError):
    """A gate asked to judge nothing refuses rather than passing."""


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    value: float | str
    threshold: float | str
    evidence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "value": self.value,
            "threshold": self.threshold,
            "evidence": self.evidence,
        }


def gate_mape_not_worse_than_naive(per_authority: Mapping[str, tuple[float, float]]) -> GateResult:
    """``per_authority``: authority to (model MAPE, seasonal naive MAPE) at horizons 1 to 24."""
    if not per_authority:
        raise GateInputError("no authorities to compare with the seasonal naive")
    worse = sorted(a for a, (model, naive) in per_authority.items() if model > naive)
    return GateResult(
        name="mape_not_worse_than_naive",
        passed=not worse,
        value=float(len(worse)),
        threshold=0.0,
        evidence=(
            f"{len(per_authority)} authorities; worse than the naive in {len(worse)}"
            + (f" ({', '.join(worse[:8])}{'...' if len(worse) > 8 else ''})" if worse else "")
        ),
    )


def gate_skill_not_significantly_negative(
    verdicts: Mapping[str, str], max_share: float = POLICY.max_share_significantly_worse_than_operator
) -> GateResult:
    """``verdicts``: authority to the skill verdict after correction (wins, loses, tie)."""
    if not verdicts:
        raise GateInputError("no skill verdicts")
    losses = sum(1 for v in verdicts.values() if v == "loses")
    share = losses / len(verdicts)
    return GateResult(
        name="skill_not_significantly_negative",
        passed=share <= max_share,
        value=share,
        threshold=max_share,
        evidence=f"significantly worse than the operator in {losses} of {len(verdicts)} comparable authorities",
    )


def gate_coverage_90_on_validation(
    coverage: float | None, band: tuple[float, float] = POLICY.coverage_band_90
) -> GateResult:
    if coverage is None:
        raise GateInputError("no validation coverage was measured")
    return GateResult(
        name="coverage_90_on_validation",
        passed=band[0] <= coverage <= band[1],
        value=coverage,
        threshold=f"{band[0]:.2f} to {band[1]:.2f}",
        evidence=f"empirical 90 percent coverage on the validation year {coverage:.3f}",
    )


def gate_peak_timing_median(
    median_hours: float | None, ceiling: float = POLICY.max_median_peak_timing_error_hours
) -> GateResult:
    if median_hours is None:
        raise GateInputError("no peak timing error was measured")
    return GateResult(
        name="peak_timing_median",
        passed=median_hours <= ceiling,
        value=median_hours,
        threshold=ceiling,
        evidence=f"median absolute peak timing error {median_hours:.1f} hours over the test year",
    )


def gate_coherence_exact(gaps_mw: Mapping[str, float], tolerance_mw: float = 1e-3) -> GateResult:
    """``gaps_mw``: reconciliation method to its largest coherence gap in megawatts."""
    if not gaps_mw:
        raise GateInputError("no reconciliation was run")
    worst = max(gaps_mw.values())
    return GateResult(
        name="coherence_exact",
        passed=worst <= tolerance_mw,
        value=worst,
        threshold=tolerance_mw,
        evidence="largest gap after reconciliation "
        + ", ".join(f"{m} {g:.6f} MW" for m, g in sorted(gaps_mw.items())),
    )


def gate_p99_latency(
    p99_ms: float | None, ceiling_ms: float = POLICY.max_p99_latency_ms, where: str = ""
) -> GateResult:
    if p99_ms is None:
        raise GateInputError("no latency was measured")
    return GateResult(
        name="p99_latency",
        passed=p99_ms <= ceiling_ms,
        value=p99_ms,
        threshold=ceiling_ms,
        evidence=f"p99 of POST /v1/forecasts {p99_ms:.0f} ms" + (f" ({where})" if where else ""),
    )


def gate_leakage_check_green(rows_checked: int, max_abs_gap: float, leaky_lag_refused: bool) -> GateResult:
    if rows_checked <= 0:
        raise GateInputError("the leakage check ran on no rows")
    passed = max_abs_gap <= 1e-9 and leaky_lag_refused
    return GateResult(
        name="leakage_check_green",
        passed=passed,
        value=max_abs_gap,
        threshold=1e-9,
        evidence=f"{rows_checked} design rows recomputed at their origin, largest gap {max_abs_gap:.2e}; "
        + ("the leaky lag was refused" if leaky_lag_refused else "the leaky lag was NOT refused"),
    )


def all_passed(results: list[GateResult]) -> bool:
    if len(results) != len(GATE_NAMES):
        raise GateInputError(f"expected {len(GATE_NAMES)} gate results, got {len(results)}")
    return all(r.passed for r in results)


def choose_served(candidates: Mapping[str, tuple[list[GateResult], float]]) -> tuple[str | None, str]:
    """``candidates``: backend to (gate results, headline figure where higher is better). The
    served backend is the passing candidate with the best headline; none if none passes."""
    if not candidates:
        raise GateInputError("no candidate backends")
    passing = {b: h for b, (results, h) in candidates.items() if all_passed(results)}
    if not passing:
        return None, "no candidate cleared every gate"
    best = max(sorted(passing), key=lambda b: passing[b])
    return best, f"{best} cleared every gate with the best headline ({passing[best]:.4f})"
