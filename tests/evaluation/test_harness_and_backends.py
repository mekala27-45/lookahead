"""The simulator's truth, the harness on known truth, the own backend and the baselines, the
protocol, and the questions of whether each step ran."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from lookahead_contracts import quarantine
from lookahead_core.config import POLICY
from lookahead_evaluation.bootstrap import (
    benjamini_hochberg,
    block_sign_flip_pvalue,
    bootstrap_statistic,
    resample_day_sums,
)
from lookahead_evaluation.harness import requests_for_test_period, run_backend, unscored_share
from lookahead_evaluation.metrics import (
    daily_peaks,
    day_sums,
    reliability,
    row_errors,
    stat_coverage_90,
    stat_mape_operator,
    stat_mase,
    stat_skill,
    sums_matrix,
)
from lookahead_evaluation.recovery import SIM_WINDOWS, run_one
from lookahead_evaluation.skill import headline, skill_table
from lookahead_forecast.baselines import SeasonalNaiveForecaster, naive_point
from lookahead_forecast.interface import QUANTILE_COLUMNS, ForecastSpec, PanelData
from lookahead_forecast.own import OwnForecaster, ProtocolError, choose_on
from lookahead_sim import GridSpec, raw_observations, simulate
from lookahead_sim.grid import _expected_operator_mape
from lookahead_sim.oracle import OracleForecaster, expected_mape

CLEAN = GridSpec(
    noise_sigma=0.0, missing_rate=0.0, cooling_evening_modulation=0.0, heating_night_modulation=0.0
)


@pytest.fixture(scope="module")
def clean_data() -> tuple[PanelData, dict[str, dict[str, float]]]:
    grid = simulate(CLEAN, 7)
    panel = quarantine.apply_rules(raw_observations(grid)).panel
    return PanelData.from_frames(panel, None, SIM_WINDOWS, "simulated"), grid.truth


@pytest.fixture(scope="module")
def own_run(clean_data: tuple[PanelData, dict[str, dict[str, float]]]) -> tuple[object, object]:
    data, _ = clean_data
    forecaster = OwnForecaster()
    spec = ForecastSpec(backend="own")
    fitted = forecaster.fit(data, spec, data.test_start)
    result = run_backend(data, forecaster, spec)
    return fitted, result


# The simulator


def test_simulator_is_seeded_and_plants_events() -> None:
    a = simulate(GridSpec(), 3)
    b = simulate(GridSpec(), 3)
    c = simulate(GridSpec(), 4)
    assert a.panel["demand_true"].to_list() == b.panel["demand_true"].to_list()
    assert a.panel["demand_true"].to_list() != c.panel["demand_true"].to_list()
    kinds = sorted(e.kind for e in a.events)
    assert kinds == sorted(["load_shed", "meter_zero", "duplicate_hour", "skipped_hours"] * 4)
    test_events = [e for e in a.events if e.window == "test"]
    validation_events = [e for e in a.events if e.window == "validation"]
    assert len(test_events) == len(validation_events) == 8
    assert all(e.start_hour >= 2 * 8760 for e in test_events), "graded events are planted in the last year"
    assert all(8760 <= e.start_hour < 2 * 8760 for e in validation_events), (
        "the threshold is chosen on events planted in the validation year"
    )


def test_operator_error_matches_its_stated_structure() -> None:
    grid = simulate(GridSpec(), 5)
    measured = (grid.panel["forecast_operator"] / grid.panel["demand_true"] - 1).abs().mean()
    assert measured == pytest.approx(_expected_operator_mape(GridSpec()), abs=0.002)


def test_subregions_sum_to_the_stated_gap() -> None:
    grid = simulate(GridSpec(), 5)
    totals = grid.subregions.group_by(["authority", "utc_hour"]).agg(pl.col("demand").sum())
    joined = totals.join(
        grid.panel.select("authority", "utc_hour", "demand_true"), on=["authority", "utc_hour"]
    )
    gap = (joined["demand"] / joined["demand_true"] - 1).mean()
    assert gap == pytest.approx(-GridSpec().subregion_gap, abs=1e-6)


# The harness on known truth


def test_harness_measures_the_known_operator_error_and_oracle_skill(
    clean_data: tuple[PanelData, dict[str, dict[str, float]]],
) -> None:
    data, truth = clean_data
    oracle = OracleForecaster(sigma=0.015, seed=1)
    result = run_backend(data, oracle, ForecastSpec(backend="oracle"))
    errors = row_errors(result.scoring)
    sums = sums_matrix(day_sums(errors))
    totals = sums.sum(axis=0, keepdims=True)
    known_operator = truth["NA1"]["operator_mape_expected"]
    assert stat_mape_operator(totals)[0] == pytest.approx(known_operator, abs=0.002)
    known_skill = 1 - expected_mape(0.015) / known_operator
    assert stat_skill(totals)[0] == pytest.approx(known_skill, abs=0.03)
    requested = sum(len(r.origin_positions) for r in requests_for_test_period(data))
    assert result.predictions.origins == requested


def test_origins_iterated_equals_test_days_times_authorities(
    own_run: tuple[object, object], clean_data: tuple[PanelData, dict[str, dict[str, float]]]
) -> None:
    data, _ = clean_data
    _, result = own_run
    # Every test day whose 48 target hours sit inside the series; the last day of the grid does not.
    days = len(requests_for_test_period(data)[0].origin_positions)
    assert days == len(data.origins(data.test_start, data.test_end, "NA1")) - 1
    assert result.predictions.origins == days * len(data.names)  # type: ignore[attr-defined]
    assert result.predictions.fits == days * len(data.names), "one expanding refit per origin"  # type: ignore[attr-defined]
    assert result.scoring.height == days * len(data.names) * POLICY.horizons  # type: ignore[attr-defined]
    assert unscored_share(result.scoring) < 0.001, "only the planted defects are unscored"  # type: ignore[attr-defined]


def test_own_recovers_thresholds_and_holiday_effect_on_clean_truth(
    own_run: tuple[object, object], clean_data: tuple[PanelData, dict[str, dict[str, float]]]
) -> None:
    _, truth = clean_data
    fitted, _ = own_run
    exact = 0
    for authority, chosen in fitted.chosen.items():  # type: ignore[attr-defined]
        t = truth[authority]
        if (
            chosen["heating_threshold_c"] == t["heating_threshold_c"]
            and chosen["cooling_threshold_c"] == t["cooling_threshold_c"]
        ):
            exact += 1
        assert abs(chosen["heating_threshold_c"] - t["heating_threshold_c"]) <= 2.0
        assert abs(chosen["cooling_threshold_c"] - t["cooling_threshold_c"]) <= 2.0
        assert chosen["chosen_on_validation"] == 1.0
        state = fitted.states[authority]  # type: ignore[attr-defined]
        beta = state.solve()
        idx = state.names.index("holiday")
        assert abs(beta[idx] / state.std[idx] - t["holiday_effect"]) <= 0.03, (
            "holiday effect within three points"
        )
    assert exact >= len(truth) // 2


def test_own_quantiles_are_calibrated_and_ordered(own_run: tuple[object, object]) -> None:
    _, result = own_run
    errors = row_errors(result.scoring)  # type: ignore[attr-defined]
    totals = sums_matrix(day_sums(errors)).sum(axis=0, keepdims=True)
    assert 0.8 <= stat_coverage_90(totals)[0] <= 0.99
    frame = result.predictions.frame  # type: ignore[attr-defined]
    for lo, hi in zip(QUANTILE_COLUMNS[:-1], QUANTILE_COLUMNS[1:], strict=True):
        assert (frame[lo] <= frame[hi]).all()
    diagram = reliability(errors)
    assert all(abs(share - level) < 0.15 for level, share, _ in diagram)


def test_the_future_is_not_read(clean_data: tuple[PanelData, dict[str, dict[str, float]]]) -> None:
    """Perturb everything after the last origin; the forecasts must not move."""
    data, _ = clean_data
    spec = ForecastSpec(backend="own")
    authority = "NA2"
    a = data.authorities[authority]
    origins = data.origins(data.test_start, data.test_end, authority)[:10]
    last = int(origins[-1])
    values = a.series.values.copy()
    values[last + 1 :] = values[last + 1 :] * 3.0 + 500.0
    tampered = PanelData.from_frames(
        pl.DataFrame(
            {
                "authority": [authority] * len(values),
                "utc_hour": [a.series.hour_at(i) for i in range(len(values))],
                "demand": values,
                "utc_offset_hours": a.offsets,
                "forecast_operator": a.operator,
                "temperature_c": a.temperature,
                "humidity_pct": a.humidity,
            }
        ).with_columns(pl.col("utc_hour").dt.replace_time_zone("UTC")),
        None,
        SIM_WINDOWS,
        "simulated",
    )
    original = PanelData(
        authorities={authority: a},
        data_source="simulated",
        training_start=data.training_start,
        validation_start=data.validation_start,
        test_start=data.test_start,
        test_end=data.test_end,
    )
    from lookahead_forecast.interface import Request

    forecaster = OwnForecaster()
    before = forecaster.predict(
        forecaster.fit(original, spec, data.test_start), original, spec, [Request(authority, origins)]
    ).frame
    after = forecaster.predict(
        forecaster.fit(tampered, spec, data.test_start), tampered, spec, [Request(authority, origins)]
    ).frame
    # Rows whose targets are at or before the last origin plus 48 hours read tampered actuals in
    # the expanding fit only after that origin; the forecasts issued at these ten origins are equal.
    np.testing.assert_allclose(before["q50"].to_numpy(), after["q50"].to_numpy(), rtol=1e-9)


def test_choosing_on_the_test_window_is_rejected() -> None:
    assert choose_on("validation") == "validation"
    with pytest.raises(ProtocolError):
        choose_on("test")


def test_windows_do_not_overlap(clean_data: tuple[PanelData, dict[str, dict[str, float]]]) -> None:
    data, _ = clean_data
    assert data.training_start < data.validation_start < data.test_start <= data.test_end


# Baselines and the skill table


def test_seasonal_naive_and_skill_table(clean_data: tuple[PanelData, dict[str, dict[str, float]]]) -> None:
    data, _ = clean_data
    result = run_backend(data, SeasonalNaiveForecaster(), ForecastSpec(backend="seasonal_naive"))
    errors = row_errors(result.scoring)
    totals = sums_matrix(day_sums(errors)).sum(axis=0, keepdims=True)
    assert stat_mase(totals)[0] == pytest.approx(1.0), "the naive scored against itself is one"
    rows = skill_table(result.scoring, 1)
    counts = headline(rows)
    assert counts["authorities"] == len(data.names)
    assert counts["wins"] + counts["losses"] + counts["ties"] == counts["authorities"]
    assert all(r.skill_lower <= r.skill <= r.skill_upper for r in rows)


def test_naive_falls_back_when_the_lag_is_quarantined(
    clean_data: tuple[PanelData, dict[str, dict[str, float]]],
) -> None:
    data, _ = clean_data
    a = data.authorities["NA1"]
    origin = np.array([5000, 5000])
    horizon = np.array([1, 2])
    values = a.series.values.copy()
    values[5001 - 168] = np.nan
    from lookahead_features.frame import SeriesIndex
    from lookahead_forecast.interface import AuthorityData

    holed = AuthorityData(
        SeriesIndex("NA1", a.series.first_hour, values),
        a.temperature,
        a.humidity,
        a.offsets,
        a.operator,
        a.region,
    )
    point = naive_point(holed, origin, horizon)
    assert point[0] == pytest.approx(values[5001 - 336])
    assert point[1] == pytest.approx(values[5002 - 168])


def test_daily_peaks_cover_the_target_day(own_run: tuple[object, object]) -> None:
    _, result = own_run
    peaks = daily_peaks(result.scoring)  # type: ignore[attr-defined]
    assert peaks.height > 300 * 8
    assert (peaks["hours"] == 24).all()
    assert peaks["model_timing_error"].abs().median() <= 2


# The bootstrap and the correction


def test_block_bootstrap_preserves_totals_in_expectation() -> None:
    sums = np.ones((100, 2))
    sums[:, 1] = np.arange(100)
    totals = resample_day_sums(sums, 7, 300, 1)
    assert totals[:, 0].mean() == pytest.approx(100.0, rel=0.02)
    point, lower, upper, n = bootstrap_statistic(sums, lambda t: t[:, 1] / t[:, 0], 1, "x")
    assert n == POLICY.bootstrap_replicates
    assert lower <= point <= upper


def test_sign_flip_finds_a_real_difference_and_not_a_null_one() -> None:
    rng = np.random.default_rng(2)
    assert block_sign_flip_pvalue(rng.normal(0.5, 1.0, 365), 7, 500, 1) < 0.01
    assert block_sign_flip_pvalue(rng.normal(0.0, 1.0, 365), 7, 500, 1) > 0.05


def test_benjamini_hochberg_rejects_the_small_p_values_only() -> None:
    rejected = benjamini_hochberg(np.array([0.001, 0.002, 0.4, 0.9, 0.04]), 0.05)
    assert rejected.tolist() == [True, True, False, False, False]
    assert benjamini_hochberg(np.array([]), 0.05).tolist() == []


# Property tests


@given(
    st.lists(st.floats(1.0, 1e5), min_size=5, max_size=50),
    st.lists(st.floats(1.0, 1e5), min_size=5, max_size=50),
)
@settings(max_examples=40, deadline=None)
def test_pinball_at_the_median_is_half_the_absolute_error(actual: list[float], forecast: list[float]) -> None:
    n = min(len(actual), len(forecast))
    a = np.asarray(actual[:n])
    f = np.asarray(forecast[:n])
    diff = a - f
    pinball = np.where(diff >= 0, 0.5 * diff, -0.5 * diff)
    np.testing.assert_allclose(pinball, 0.5 * np.abs(diff))


@given(st.lists(st.floats(0.0, 1.0), min_size=1, max_size=100))
@settings(max_examples=40, deadline=None)
def test_coverage_is_in_the_unit_interval(shares: list[float]) -> None:
    hits = np.asarray(shares) > 0.5
    assert 0.0 <= hits.mean() <= 1.0


def test_recovery_run_reports_every_figure() -> None:
    record = run_one("base", 0)
    for key in (
        "harness.skill_bias",
        "harness.interval_covers_known",
        "own.coverage_90",
        "own.thresholds_within_2c",
    ):
        assert key in record.figures
    assert record.figures["harness.origins"] == 363 * 8


def test_gbm_refits_are_checkpointed_and_read_back_identically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The build machine restarts without notice; with the checkpoint directory set, a refit's
    booster is saved and the rerun loads the booster that was trained, so the predictions match."""
    from lookahead_forecast.gbm import CHECKPOINT_ENV, _train_or_load

    monkeypatch.setenv(CHECKPOINT_ENV, str(tmp_path))
    generator = np.random.default_rng(0)
    x = generator.normal(size=(400, 3))
    y = x[:, 0] * 0.5 + generator.normal(scale=0.1, size=400) + 1.0
    spec = ForecastSpec(backend="gbm", seed=1, gbm_rounds=5)
    names = ["a", "b", "c"]
    first = _train_or_load("2025-01-01", "grid-abc", x, y, names, spec, 1)
    assert (tmp_path / f"{spec.spec_hash}-grid-abc-2025-01-01.ubj").exists()
    again = _train_or_load(
        "2025-01-01", "grid-abc", x, y, names, spec, 999
    )  # a different seed: not retrained
    # Another population with the same spec trains its own booster rather than reading this one.
    other = _train_or_load("2025-01-01", "households-def", x[:200], y[:200], names, spec, 1)
    assert (tmp_path / f"{spec.spec_hash}-households-def-2025-01-01.ubj").exists()
    assert other[0] is not again[0]
    p1 = np.asarray(first[0].inplace_predict(x[:10]))  # type: ignore[attr-defined]
    p2 = np.asarray(again[0].inplace_predict(x[:10]))  # type: ignore[attr-defined]
    np.testing.assert_array_equal(p1, p2)


def test_recovery_records_are_checkpointed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from lookahead_evaluation import recovery

    monkeypatch.setenv(recovery.CHECKPOINT_ENV, str(tmp_path))
    calls: list[tuple[str, int]] = []

    def fake_run_one(condition: str, seed: int) -> recovery.RunRecord:
        calls.append((condition, seed))
        return recovery.RunRecord(
            condition=condition, seed=seed, figures={"x": 1.5}, per_authority=[{"a": 1}]
        )

    monkeypatch.setattr(recovery, "run_one", fake_run_one)
    first = recovery.run_study(["base"], 2, workers=1)
    second = recovery.run_study(["base"], 2, workers=1)
    assert calls == [("base", 0), ("base", 1)]
    assert [r.figures for r in second] == [r.figures for r in first]
    assert second[0].per_authority == [{"a": 1}]
