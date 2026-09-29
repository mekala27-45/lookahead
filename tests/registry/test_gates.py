"""Every registry gate: a clean pass, a deliberate violation, and a refusal on nothing."""

from __future__ import annotations

import pytest
from lookahead_registry.gates import (
    GATE_NAMES,
    GateInputError,
    GateResult,
    all_passed,
    choose_served,
    gate_coherence_exact,
    gate_coverage_90_on_validation,
    gate_leakage_check_green,
    gate_mape_not_worse_than_naive,
    gate_p99_latency,
    gate_peak_timing_median,
    gate_skill_not_significantly_negative,
)


def test_mape_gate() -> None:
    assert gate_mape_not_worse_than_naive({"A": (0.02, 0.05), "B": (0.03, 0.03)}).passed
    failed = gate_mape_not_worse_than_naive({"A": (0.02, 0.05), "B": (0.06, 0.03)})
    assert not failed.passed and "B" in failed.evidence
    with pytest.raises(GateInputError):
        gate_mape_not_worse_than_naive({})


def test_skill_gate() -> None:
    assert gate_skill_not_significantly_negative(
        {"A": "wins", "B": "loses", "C": "tie"}, max_share=0.5
    ).passed
    assert not gate_skill_not_significantly_negative(
        {"A": "loses", "B": "loses", "C": "tie"}, max_share=0.5
    ).passed
    with pytest.raises(GateInputError):
        gate_skill_not_significantly_negative({})


def test_coverage_gate() -> None:
    assert gate_coverage_90_on_validation(0.9).passed
    assert not gate_coverage_90_on_validation(0.80).passed
    assert not gate_coverage_90_on_validation(0.99).passed
    with pytest.raises(GateInputError):
        gate_coverage_90_on_validation(None)


def test_peak_timing_gate() -> None:
    assert gate_peak_timing_median(1.0).passed
    assert not gate_peak_timing_median(3.0).passed
    with pytest.raises(GateInputError):
        gate_peak_timing_median(None)


def test_coherence_gate() -> None:
    assert gate_coherence_exact({"bottom_up": 0.0, "mint": 1e-8}).passed
    assert not gate_coherence_exact({"bottom_up": 0.0, "mint": 13.3}).passed
    with pytest.raises(GateInputError):
        gate_coherence_exact({})


def test_latency_gate() -> None:
    assert gate_p99_latency(800.0).passed
    assert not gate_p99_latency(2500.0).passed
    with pytest.raises(GateInputError):
        gate_p99_latency(None)


def test_leakage_gate() -> None:
    assert gate_leakage_check_green(60, 0.0, True).passed
    assert not gate_leakage_check_green(60, 1e-3, True).passed
    assert not gate_leakage_check_green(60, 0.0, False).passed
    with pytest.raises(GateInputError):
        gate_leakage_check_green(0, 0.0, True)


def _results(passed: bool) -> list[GateResult]:
    return [GateResult(name, passed, 0.0, 0.0, "test") for name in GATE_NAMES]


def test_served_is_the_passing_candidate_with_the_best_headline() -> None:
    assert all_passed(_results(True))
    assert not all_passed([*_results(True)[:-1], GateResult(GATE_NAMES[-1], False, 1.0, 0.0, "t")])
    with pytest.raises(GateInputError):
        all_passed(_results(True)[:3])
    served, _ = choose_served({"own": (_results(True), 10.0), "gbm": (_results(True), 12.0)})
    assert served == "gbm"
    served, _ = choose_served({"own": (_results(True), 10.0), "gbm": (_results(False), 12.0)})
    assert served == "own"
    served, reason = choose_served({"own": (_results(False), 10.0)})
    assert served is None and "no candidate" in reason
    with pytest.raises(GateInputError):
        choose_served({})
