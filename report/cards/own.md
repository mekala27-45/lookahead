# Model card: own, the per authority ridge backend

Rendered from `results/manifest.json` by the claim gate; do not edit by hand. The contract below
is the one `docs/serving.md` sets out, and every figure is a manifest value or table.

## Intended use

The own backend forecasts hourly demand for each of the 51 balancing
authorities in the backtest, 1 to 48 hours after a daily origin at
0:00 UTC, with quantiles at 0.05, 0.25, 0.50, 0.75, 0.95. It is one
of the two candidates the registry judges and the fallback the API serves when no candidate clears
every gate. It is meant for the demonstration of a day ahead process on EIA-930 data and for the
detector's residuals. It is not meant for grid operations, for any authority it was not fit on, for
horizons past two days, or for a live desk that has a weather forecast rather than the weather that
happened.

## Data and population

EIA-930 hourly demand from 2018-07-01 05:00:00+00:00 to 2026-09-30 07:00:00+00:00 for the
51 authorities with at least 90%
clean coverage in both the validation and the test year, quarantined by named rules
(1.113% of rows), with Open-Meteo hourly temperature and humidity at
one stated location per authority (observed weather, stated on every figure). Training from
2018-07-01, validation from 2024-09-29, test
2025-09-29 to 2026-09-28.

## How it was fit

Per authority, a ridge regression of the ratio of demand to the scale (the mean of the week ending
at the origin) on Fourier terms (daily, weekly, yearly), day type and holiday dummies, lags at the
horizon's availability, heating and cooling degree hours against thresholds chosen on the validation
year from 36 candidate pairs, and their change against the
same hour lag, with the ridge penalty chosen on validation from 0.1, 1, 10, 100, 1000, 10000
(29,325 static fits in the search); then an expanding fit over every
origin through an incremental Gram matrix (18,615 solves over
18,615 origins in 312.8 seconds of fitting and
16.3 of prediction). Quantiles by relative conformal residual
quantiles per 6 hour horizon bucket, calibrated on the
validation year. Chosen on validation: yes. Version
`own-a6c87a9b`.

## Metrics

| | Value | Interval |
|---|---:|---:|
| MAPE, all horizons | 5.65% | 5.25% to 6.07% |
| Seasonal naive MAPE | 11.66% | |
| Operator MAPE, paired hours | 13.59% | |
| MASE | 0.426 | 0.410 to 0.444 |
| CRPS | 3.89% | 3.54% to 4.24% |
| 90 percent coverage, test | 88.3% | 87.6% to 89.1% |
| 90 percent coverage, validation | 90.1% | |
| Wins against the operator, horizons 1 to 24 | 14 of 44 | 9 to 19 |
| Losses against the operator | 21 | 16 to 26 |
| Median peak timing error | 1.0 h h | |

Source: real:eia930, model own, 51 authorities in the backtest, test year, as of 2026-09-29.

On the simulator with known truth, the heating and cooling thresholds are recovered within 2 C in
97% of authorities on the base condition and the
90 percent coverage is 90.3%; the holiday effect's absolute error is
1.05%.

## The integration contract

A ticked line is met. Any other line names what it is instead: partly met, not built, or not
applicable, with the reason.

- [x] **trained**: fit through the validation year and refit at every test origin; 18,615 solves.
- [x] **timed**: 332.8 seconds for the backtest, 3,356.3 origins a minute on CPU.
- [x] **calibrated**: conformal offsets on the validation year; 90 percent coverage 90.1% on validation and 88.3% on test.
- [x] **useful**: beats the seasonal naive (5.65% against 11.66%) and the operator in 14 authorities.
- [ ] **fair**: not applicable in the sense of protected groups; the comparability rule keeps the operator comparison honest per authority, which is the fairness this model can offer.
- [x] **gated**: 7 of 7 gates passed (yes); the table is in `RESULTS.md`.
- [x] **served**: the export `results/models/own_model.json` is what the API loads when the registry names own or when no candidate passes; the registry's choice is gbm.
- [x] **integrated**: `POST /v1/forecasts` issues from the served export; the site's authority pages issue through it.
- [x] **monitored**: every issued forecast is stored and scored when actuals arrive; the scorecard reports the unscored share.
- [x] **documented**: this card, `docs/protocol.md`, `docs/definitions.md`.
- [x] **bounded**: the intended use above; observed weather, two day horizon, the authorities it was fit on.
- [x] **validated**: proven on the simulator first (thresholds recovered, coverage against nominal) and on 120 recovery runs.
- [x] **explainable at the decision**: every coefficient is in `results/backtest/own/coefficients.parquet` and the chosen thresholds per authority in the manifest.

## Limitations

Observed weather at the target hour stands in for a weather forecast, so the error is a lower
bound on a live desk's and the wins against the operator an upper bound. One model per authority
learns nothing across authorities. The threshold search is a grid; the temperature response is a
hinge, not a spline. The conformal offsets are frozen at the end of the validation year and do not
adapt through the test year. The degenerate level count is none.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
