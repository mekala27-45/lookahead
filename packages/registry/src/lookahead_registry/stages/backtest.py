"""Stage: the rolling origin backtest of one backend on the real grid, with the two baselines.

Fits the backend through the validation year, runs it over every test origin of every
authority in the backtest, and writes results/backtest/<backend>/predictions.parquet and
scoring.parquet, the summary tables, and results/manifests/backtest_<backend>.json. The
seasonal naive runs alongside so its figures sit in the same manifest as the backend's.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any

import polars as pl
from lookahead_core.config import POLICY, QUANTILE_LEVELS
from lookahead_core.manifest import Manifest, Scalar, Scribe
from lookahead_core.paths import Paths
from lookahead_core.statements import WEATHER_CAVEAT
from lookahead_evaluation.harness import RunResult, run_backend
from lookahead_evaluation.summary import Summary, summarise
from lookahead_forecast.baselines import SeasonalNaiveForecaster
from lookahead_forecast.interface import QUANTILE_COLUMNS, Forecaster, ForecastSpec, PanelData
from lookahead_forecast.own import OwnForecaster
from lookahead_forecast.serve import export_gbm, export_own, write_bundle

from lookahead_registry.stages.data import load_panel, load_windows

BACKENDS: dict[str, type] = {"own": OwnForecaster, "seasonal_naive": SeasonalNaiveForecaster}


def register_backend(name: str, cls: type) -> None:
    BACKENDS[name] = cls


def load_data(paths: Paths, eligible_only: bool = True) -> PanelData:
    panel = load_panel(paths)
    authorities = pl.read_csv(paths.eia / "authorities.csv")
    if eligible_only:
        keep = authorities.filter(pl.col("backtest_eligible"))["authority"].to_list()
        panel = panel.filter(pl.col("authority").is_in(keep))
    weather = pl.read_parquet(paths.weather / "hourly.parquet")
    return PanelData.from_frames(panel, weather, load_windows(paths), "real:eia930")


def make_forecaster(name: str) -> Forecaster:
    try:
        from lookahead_forecast.gbm import GbmForecaster

        BACKENDS.setdefault("gbm", GbmForecaster)
    except ImportError:
        pass
    if name not in BACKENDS:
        raise KeyError(f"unknown backend {name!r}; choose from {sorted(BACKENDS)}")
    forecaster: Forecaster = BACKENDS[name]()
    return forecaster


def run(
    paths: Paths,
    as_of: str,
    seed: int,
    backend: str,
    *,
    data: PanelData | None = None,
    authorities: list[str] | None = None,
    rescore: bool = False,
) -> Manifest:
    data = data or load_data(paths)
    if authorities:
        data = PanelData(
            authorities={k: v for k, v in data.authorities.items() if k in authorities},
            data_source=data.data_source,
            training_start=data.training_start,
            validation_start=data.validation_start,
            test_start=data.test_start,
            test_end=data.test_end,
            truth=data.truth,
        )
    spec = ForecastSpec(backend=backend, seed=seed)
    folder = paths.results / "backtest" / backend
    folder.mkdir(parents=True, exist_ok=True)
    started = time.time()
    if rescore:
        # The saved predictions scored again against the current panel; nothing is refit.
        from lookahead_evaluation.harness import scoring_frame
        from lookahead_forecast.interface import Predictions

        saved = pl.read_parquet(folder / "predictions.parquet")
        timing = (
            json.loads((folder / "timing.json").read_text(encoding="utf-8"))
            if (folder / "timing.json").exists()
            else {}
        )
        predictions = Predictions(
            frame=saved,
            backend=backend,
            spec_hash=spec.spec_hash,
            data_source=data.data_source,
            fits=int(timing.get("fits", 0)),
            origins=int(saved.select("authority", "origin").unique().height),
        )
        result = RunResult(
            predictions=predictions,
            scoring=scoring_frame(data, saved),
            fit_seconds=float(timing.get("fit_seconds", 0.0)),
            predict_seconds=float(timing.get("predict_seconds", 0.0)),
            fitted=None,
        )
        seconds = float(timing.get("run_seconds", 0.0))
    else:
        forecaster = make_forecaster(backend)
        result = run_backend(data, forecaster, spec)
        seconds = time.time() - started
        result.predictions.frame.write_parquet(folder / "predictions.parquet", compression="zstd")
        (folder / "timing.json").write_text(
            json.dumps(
                {
                    "fits": result.predictions.fits,
                    "fit_seconds": result.fit_seconds,
                    "predict_seconds": result.predict_seconds,
                    "run_seconds": seconds,
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
    result.scoring.write_parquet(folder / "scoring.parquet", compression="zstd")
    summary = summarise(result.scoring, seed, backend)
    (folder / "summary.json").write_text(
        json.dumps(_summary_payload(summary), indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )

    manifest = Manifest(as_of=as_of, seed=seed)
    model = backend if backend in ("own", "gbm", "seasonal_naive") else "none"
    w = Scribe(
        manifest,
        source=data.data_source,
        model=model,
        population=f"{len(data.names)} authorities in the backtest, test year",
        origin="lookahead_registry.stages.backtest",
    )
    prefix = f"backtest.{backend}"
    _write_summary(w, prefix, summary, result, seconds)
    if backend == "own" and result.fitted is not None:
        _own_choices(w, prefix, result.fitted, data, folder)
        export_own(result.fitted, data, spec, paths.results / "models" / "own_model.json")
    if backend == "gbm" and result.fitted is not None:
        _gbm_details(w, prefix, result.fitted, folder)
        export_gbm(result.fitted, data, spec, paths.results / "models" / "gbm_model.json")
    if result.fitted is not None and backend in ("own", "gbm"):
        write_bundle(data, paths.results / "models" / "serving_bundle.parquet")
    if result.fitted is None and (folder / "details.json").exists():
        _replay_details(w, prefix, folder)
    elif result.fitted is not None:
        _keep_details(manifest, prefix, folder)
    manifest.save(paths.results / "manifests" / f"backtest_{backend}.json")
    return manifest


def _summary_payload(summary: Summary) -> dict[str, object]:
    return {
        "overall": {k: asdict(v) for k, v in summary.overall.items()},
        "by_authority": summary.by_authority,
        "by_horizon": summary.by_horizon,
        "by_local_hour": summary.by_local_hour,
        "reliability": summary.reliability,
        "peaks": {k: asdict(v) for k, v in summary.peaks.items()},
        "peaks_by_authority": summary.peaks_by_authority,
        "interior": summary.interior,
        "degenerate_levels": summary.degenerate_levels,
        "rows_scored": summary.rows_scored,
        "rows_unscored": summary.rows_unscored,
    }


def _write_summary(w: Scribe, prefix: str, summary: Summary, result: RunResult, seconds: float) -> None:
    w.put(f"{prefix}.origins", result.predictions.origins, "int")
    w.put(f"{prefix}.fits", result.predictions.fits, "int")
    w.put(f"{prefix}.rows_scored", summary.rows_scored, "int")
    w.put(f"{prefix}.rows_unscored", summary.rows_unscored, "int")
    w.put(
        f"{prefix}.unscored_share",
        summary.rows_unscored / max(summary.rows_scored + summary.rows_unscored, 1),
        "pct2",
    )
    w.put(f"{prefix}.fit_seconds", result.fit_seconds, "float1")
    w.put(f"{prefix}.predict_seconds", result.predict_seconds, "float1")
    w.put(f"{prefix}.run_seconds", seconds, "float1")
    w.put(f"{prefix}.origins_per_minute", result.predictions.origins / max(seconds / 60.0, 1e-9), "float1")
    w.put(f"{prefix}.weather_caveat", WEATHER_CAVEAT, "text")
    fmt = {
        "mape": "pct2",
        "mape_operator": "pct2",
        "mape_naive": "pct2",
        "mase": "float3",
        "crps": "pct2",
        "coverage_50": "pct1",
        "coverage_90": "pct1",
    }
    for name, stat in summary.overall.items():
        f = fmt.get(name, "pct3")
        w.put(f"{prefix}.{name}", stat.value, f)
        w.put(f"{prefix}.{name}_lower", stat.lower, f)
        w.put(f"{prefix}.{name}_upper", stat.upper, f)
    w.put(
        f"{prefix}.skill_vs_naive",
        1.0 - summary.overall["mape"].value / summary.overall["mape_naive"].value,
        "pct1",
    )
    rows: list[list[Scalar]] = [
        [
            r["authority"],
            r["hours"],
            r["mape"],
            r["mape_lower"],
            r["mape_upper"],
            r["mape_operator"],
            r["mape_naive"],
            r["mase"],
            r["crps"],
            r["coverage_50"],
            r["coverage_90"],
        ]
        for r in summary.by_authority
    ]
    w.table(
        f"{prefix}.by_authority",
        [
            "Authority",
            "Hours",
            "MAPE",
            "lower",
            "upper",
            "Operator MAPE",
            "Seasonal naive MAPE",
            "MASE",
            "CRPS",
            "50 pct coverage",
            "90 pct coverage",
        ],
        ["text", "int", "pct2", "pct2", "pct2", "pct2", "pct2", "float3", "pct2", "pct1", "pct1"],
        rows,
    )
    w.table(
        f"{prefix}.by_horizon",
        [
            "Horizon (h)",
            "MAPE",
            "Operator MAPE",
            "Seasonal naive MAPE",
            "CRPS",
            "50 pct coverage",
            "90 pct coverage",
        ],
        ["int", "pct2", "pct2", "pct2", "pct2", "pct1", "pct1"],
        [
            [
                r["horizon"],
                r["mape"],
                r["mape_operator"],
                r["mape_naive"],
                r["crps"],
                r["coverage_50"],
                r["coverage_90"],
            ]
            for r in summary.by_horizon
        ],
    )
    w.table(
        f"{prefix}.by_local_hour",
        ["Local hour", "MAPE", "Operator MAPE", "Seasonal naive MAPE", "90 pct coverage"],
        ["int", "pct2", "pct2", "pct2", "pct1"],
        [
            [r["local_hour"], r["mape"], r["mape_operator"], r["mape_naive"], r["coverage_90"]]
            for r in summary.by_local_hour
        ],
    )
    w.table(
        f"{prefix}.reliability",
        ["Level", "Share of actuals at or below", "Rows"],
        ["pct0", "pct1", "int"],
        [[q, share, n] for q, share, n in summary.reliability],
    )
    for q, c in zip(QUANTILE_LEVELS, QUANTILE_COLUMNS, strict=True):
        w.put(
            f"{prefix}.reliability.{c}",
            next(share for lvl, share, _ in summary.reliability if abs(lvl - q) < 1e-9),
            "pct1",
        )
    w.table(
        f"{prefix}.interior",
        ["Level", "Share of actuals below", "Interior"],
        ["pct0", "pct1", "text"],
        [[r["level"], r["share_below"], r["interior"]] for r in summary.interior],
    )
    w.put(f"{prefix}.degenerate_levels", ", ".join(summary.degenerate_levels) or "none", "text")
    w.put(f"{prefix}.levels_interior", "yes" if not summary.degenerate_levels else "no", "text")
    if summary.peaks:
        pk = summary.peaks
        for name, f in (
            ("model_peak_abs", "pct2"),
            ("operator_peak_abs", "pct2"),
            ("naive_peak_abs", "pct2"),
            ("model_timing_abs", "hours1"),
            ("operator_timing_abs", "hours1"),
            ("model_morning_abs", "pct2"),
            ("operator_morning_abs", "pct2"),
            ("model_evening_abs", "pct2"),
            ("operator_evening_abs", "pct2"),
        ):
            w.put(f"{prefix}.peaks.{name}", pk[name].value, f)
            w.put(f"{prefix}.peaks.{name}_lower", pk[name].lower, f)
            w.put(f"{prefix}.peaks.{name}_upper", pk[name].upper, f)
        w.put(f"{prefix}.peaks.model_timing_median", pk["model_timing_median"].value, "hours1")
        w.put(f"{prefix}.peaks.operator_timing_median", pk["operator_timing_median"].value, "hours1")
        w.table(
            f"{prefix}.peaks_by_authority",
            [
                "Authority",
                "Days",
                "Peak error",
                "Operator peak error",
                "Naive peak error",
                "Peak timing error",
                "Operator timing error",
                "Median timing error",
                "Morning ramp error",
                "Operator morning ramp",
                "Evening ramp error",
                "Operator evening ramp",
            ],
            [
                "text",
                "int",
                "pct2",
                "pct2",
                "pct2",
                "hours1",
                "hours1",
                "hours1",
                "pct2",
                "pct2",
                "pct2",
                "pct2",
            ],
            [
                [
                    r["authority"],
                    r["days"],
                    r["model_peak_abs"],
                    r["operator_peak_abs"],
                    r["naive_peak_abs"],
                    r["model_timing_abs"],
                    r["operator_timing_abs"],
                    r["model_timing_median"],
                    r["model_morning_abs"],
                    r["operator_morning_abs"],
                    r["model_evening_abs"],
                    r["operator_evening_abs"],
                ]
                for r in summary.peaks_by_authority
            ],
        )


def _own_choices(w: Scribe, prefix: str, fitted: Any, data: PanelData, folder: object) -> None:
    """The thresholds and penalties chosen on validation, per authority, and the search grid."""
    from pathlib import Path

    rows: list[list[Scalar]] = []
    grid_rows = []
    for authority in data.names:
        c = fitted.chosen[authority]
        rows.append(
            [
                authority,
                c["heating_threshold_c"],
                c["cooling_threshold_c"],
                c["ridge_penalty"],
                c["validation_mape"],
            ]
        )
        for g in fitted.search[authority]:
            grid_rows.append({"authority": authority, **g})
    w.table(
        f"{prefix}.chosen",
        ["Authority", "Heating threshold (C)", "Cooling threshold (C)", "Ridge penalty", "Validation MAPE"],
        ["text", "float1", "float1", "float2", "pct2"],
        rows,
    )
    w.put(
        f"{prefix}.chosen_on_validation",
        "yes" if all(fitted.chosen[a]["chosen_on_validation"] == 1.0 for a in data.names) else "no",
        "text",
    )
    w.put(
        f"{prefix}.threshold_candidates",
        len(POLICY.heating_thresholds_c) * len(POLICY.cooling_thresholds_c),
        "int",
    )
    w.put(f"{prefix}.search_fits", fitted.fits, "int")
    pl.DataFrame(grid_rows).write_parquet(Path(str(folder)) / "threshold_search.parquet")
    coefficients = []
    for authority in data.names:
        state = fitted.states[authority]
        beta = state.solve()
        for name, b, sd in zip(state.names, beta, state.std, strict=True):
            coefficients.append(
                {
                    "authority": authority,
                    "feature": name,
                    "coefficient_standardized": float(b),
                    "coefficient": float(b / sd) if sd else float(b),
                }
            )
    pl.DataFrame(coefficients).write_parquet(Path(str(folder)) / "coefficients.parquet")


def _gbm_details(w: Scribe, prefix: str, fitted: Any, folder: object) -> None:
    """Refit dates, training rows per refit, the thinning, and the feature importance of the calibration fit."""
    from pathlib import Path

    from lookahead_forecast.gbm import ORIGIN_DAY_THINNING, feature_importance

    refits = [k for k in fitted.boosters if k != "calibration"]
    w.put(f"{prefix}.refits", len(refits), "int")
    w.put(f"{prefix}.refit_dates", ", ".join(refits), "text")
    w.put(f"{prefix}.origin_day_thinning", ORIGIN_DAY_THINNING, "int")
    w.put(f"{prefix}.calibration_rows", fitted.calibration_rows, "int")
    w.put(f"{prefix}.training_rows_calibration", fitted.training_rows_by_refit.get("calibration", 0), "int")
    w.put(
        f"{prefix}.training_rows_first_refit",
        fitted.training_rows_by_refit.get(refits[0], 0) if refits else 0,
        "int",
    )
    importance = feature_importance(fitted)
    w.table(
        f"{prefix}.importance",
        ["Feature", "Share of gain"],
        ["text", "pct1"],
        [[name, share] for name, share in importance[:15]],
    )
    pl.DataFrame(
        {"feature": [n for n, _ in importance], "share_of_gain": [g for _, g in importance]}
    ).write_parquet(Path(str(folder)) / "importance.parquet")


def _keep_details(manifest: Manifest, prefix: str, folder: object) -> None:
    """The backend specific entries (choices, importance) saved beside the predictions so a rescore keeps them."""
    from pathlib import Path

    details = {
        "values": {
            k: v.model_dump(mode="json")
            for k, v in manifest.values.items()
            if k.startswith(f"{prefix}.chosen")
            or k.startswith(f"{prefix}.threshold")
            or k.startswith(f"{prefix}.search")
            or k.startswith(f"{prefix}.refit")
            or k.startswith(f"{prefix}.origin_day")
            or k.startswith(f"{prefix}.calibration")
            or k.startswith(f"{prefix}.training")
        },
        "tables": {
            k: v.model_dump(mode="json")
            for k, v in manifest.tables.items()
            if k in (f"{prefix}.chosen", f"{prefix}.importance")
        },
    }
    (Path(str(folder)) / "details.json").write_text(
        json.dumps(details, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )


def _replay_details(w: Scribe, prefix: str, folder: object) -> None:
    from pathlib import Path

    from lookahead_core.manifest import TableEntry, ValueEntry

    details = json.loads((Path(str(folder)) / "details.json").read_text(encoding="utf-8"))
    for key, payload in details["values"].items():
        entry = ValueEntry.model_validate(payload)
        w.manifest.values[key] = entry
    for key, payload in details["tables"].items():
        w.manifest.tables[key] = TableEntry.model_validate(payload)
