# Model card: gbm, the global gradient boosted backend

Rendered from `results/manifest.json` by the claim gate; do not edit by hand. The contract below
is the one `docs/serving.md` sets out, and every figure is a manifest value or table.

## Intended use

The gbm backend forecasts hourly demand for every balancing authority in the backtest with one
model, 1 to 48 hours after a daily origin at 0:00
UTC, with quantiles at 0.05, 0.25, 0.50, 0.75, 0.95. It is one of the two candidates the
registry judges. It is meant for the demonstration of a day ahead process on EIA-930 data. It is
not meant for grid operations, for authorities outside the backtest, for horizons past two days, or
for a live desk that has a weather forecast rather than the weather that happened.

## Data and population

The same panel as own: EIA-930 hourly demand for the 51 backtest
authorities with Open-Meteo observed weather, training from 2018-07-01,
validation from 2024-09-29, test 2025-09-29 to
2026-09-28, with the authority and its region as categorical features.

## How it was fit

One XGBoost booster with the quantile objective at the five served levels, on the same ratio target
and point in time features as own plus the authority and region codes, trained on every
3 origin days of the previous 1,096
days and refit at the start of every calendar month of the test year (13
refits: 2025-09-01, 2025-10-01, 2025-11-01, 2025-12-01, 2026-01-01, 2026-02-01, 2026-03-01, 2026-04-01, 2026-05-01, 2026-06-01, 2026-07-01, 2026-08-01, 2026-09-01; 2,677,186 rows in the
calibration fit). Intervals conformalized per 6 hour
bucket on the validation year (891,769 calibration rows). The
backtest took 4,356.0 seconds over 18,615 origins.
LightGBM was the brief's choice and the first implementation; its quantile objective refit too
slowly for the day and XGBoost's vector quantile objective replaced it (`DECISIONS.md`). Version
`gbm-c39d958f`.

## Metrics

| | Value | Interval |
|---|---:|---:|
| MAPE, all horizons | 5.48% | 5.01% to 5.98% |
| Seasonal naive MAPE | 11.66% | |
| Operator MAPE, paired hours | 13.59% | |
| MASE | 0.404 | 0.391 to 0.422 |
| CRPS | 3.80% | 3.40% to 4.24% |
| 90 percent coverage, test | 89.1% | 88.6% to 89.6% |
| 90 percent coverage, validation | 90.0% | |
| Wins against the operator, horizons 1 to 24 | 18 of 44 | 13 to 24 |
| Losses against the operator | 17 | 12 to 22 |
| Median peak timing error | 1.0 h h | |

Source: real:eia930, model gbm, 51 authorities in the backtest, test year, as of 2026-09-29.

| Feature | Share of gain |
|---|---:|
| r_same_hour | 50.1% |
| r_week | 7.2% |
| authority_code | 5.9% |
| r_two_weeks | 5.0% |
| obs_cooling_change | 4.2% |
| obs_temperature_scaled | 3.8% |
| obs_heating_change | 3.8% |
| r_same_hour_prev | 3.0% |
| r_origin | 2.5% |
| obs_cooling_degree | 2.3% |
| obs_cooling_x_day_sin | 2.2% |
| obs_heating_degree | 1.9% |
| week_sin_1 | 1.7% |
| weekend | 0.9% |
| r_mean_24 | 0.8% |

Source: real:eia930, model gbm, 51 authorities in the backtest, test year, as of 2026-09-29.

## The integration contract

A ticked line is met. Any other line names what it is instead: partly met, not built, or not
applicable, with the reason.

- [x] **trained**: a calibration fit before the validation year and 13 monthly refits through the test year.
- [x] **timed**: 4,356.0 seconds for the backtest, 256.4 origins a minute on CPU.
- [x] **calibrated**: conformalized intervals on the validation year; 90 percent coverage 90.0% on validation and 89.1% on test.
- [x] **useful**: MAPE 5.48% against the seasonal naive's 11.66%; wins against the operator in 18 authorities.
- [ ] **fair**: not applicable in the sense of protected groups; the comparability rule keeps the operator comparison honest per authority.
- [x] **gated**: 7 of 7 gates passed (yes).
- [x] **served**: the export `results/models/gbm_model.json` with its booster is what the API loads when the registry names gbm; the registry's choice is gbm.
- [x] **integrated**: the same `POST /v1/forecasts` route serves whichever export the registry names.
- [x] **monitored**: the forecast log and scorecard as for own.
- [x] **documented**: this card, `docs/protocol.md`.
- [x] **bounded**: the intended use above; every 3 origin days in training, stated.
- [x] **validated**: the cross check against own on the same rows (8 disagreements on the operator) and the leakage check shared with own.
- [x] **explainable at the decision**: the feature importance table above and the per row quantiles stored with every issued forecast.

## Limitations

Observed weather, as for own. A global model pools authorities that behave differently; the
authority code is a categorical feature, not a separate model. Training on every
3 origin days was a compute decision for the day and is
stated. The monthly refit is a stated schedule, not a data driven one. The booster is the last
refit's, so the API forecasts with a model fit at the start of the last test month.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
