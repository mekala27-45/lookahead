# Model card: the meter model: gbm over the household clusters, reconciled

Rendered from `results/manifest.json` by the claim gate; do not edit by hand. The contract below
is the one `docs/serving.md` sets out, and every figure is a manifest value or table.

## Intended use

The meter model forecasts the hourly load of each of the 3 load shape clusters
and of the panel total for a fixed panel of 4,485 London households,
1 to 48 hours ahead of a daily origin, reconciled to the total by MinT. It is
the second hierarchy in the build and is meant to show bottom up forecasting at the meter and what
reconciliation does to it. It is not meant for any live tariff, for households outside the panel,
for 2026, or for half hourly settlement.

## Data and population

The Low Carbon London release (167,932,474 readings, 5,566
households, 2011-11-23 09:00:00 to 2014-02-28 00:00:00), read through DuckDB; the
4,485 households reporting through the whole forecast window
(84% of those profiled), summed hourly per cluster and in total.
No weather. Test period 2013-12-01 to 2014-02-28, the
year before as validation.

## How it was fit

The gbm backend on the cluster panel as if the clusters were authorities: one booster with the
quantile objective at the five levels, 4 fits over
352 origins, conformalized on the validation year; MinT with the shrunk
covariance of the calibration model's validation residuals (intensity
0.00). Hourly rather than half hourly because the
forecasting interface is hourly (`DECISIONS.md`).

## Metrics

| Level | Method | MAPE | lower | upper | 90 pct coverage |
|---|---|---:|---:|---:|---:|
| panel total | base | 4.30% | 3.76% | 5.05% | 98.6% |
| panel total | bottom_up | 4.27% | 3.73% | 4.92% | 98.9% |
| panel total | mint | 4.26% | 3.73% | 4.89% | 98.8% |
| clusters | base | 6.78% | 5.94% | 7.61% | 97.8% |
| clusters | bottom_up | 6.78% | 5.84% | 7.59% | 97.8% |
| clusters | mint | 9.12% | 7.46% | 10.73% | 92.6% |

Source: real:lcl, model gbm, 4485 households reporting through the whole forecast window, 352 origins, as of 2026-09-29.

MinT helped at the total (+0.05%
points of MAPE) and hurt at the clusters
(-2.34%); coherence gaps bottom up
0.000000 kWh and MinT 0.000000 kWh.

## The integration contract

A ticked line is met. Any other line names what it is instead: partly met, not built, or not
applicable, with the reason.

- [x] **trained**: 4 fits over 352 origins.
- [x] **timed**: part of the meter stage's 98.1 seconds.
- [x] **calibrated**: conformalized on the validation year; 90 percent coverage 98.6% at the total on test.
- [x] **useful**: MAPE 4.30% at the total before reconciliation and 4.26% after.
- [ ] **fair**: not applicable; the clusters are load shapes, not people, and no household identifier is published.
- [ ] **gated**: not built; the registry's gates judge the grid backends, and the meter model is not served.
- [ ] **served**: not applicable; the meter model is an analysis, not an API route.
- [ ] **integrated**: not applicable, as above.
- [ ] **monitored**: not applicable; there is no live meter feed.
- [x] **documented**: this card and `docs/meter.md`.
- [x] **bounded**: the intended use above; the fixed panel and the hourly resolution are stated.
- [x] **validated**: coherence to the kilowatt hour and accuracy before and after by level with block bootstrap intervals.
- [x] **explainable at the decision**: the clusters are described by shape and share; the reconciled total is beside the base one at every origin in `results/meter/forecast_total.parquet`.

## Limitations

A fixed panel of 4,485 households is a stated subsample of the release.
No weather, so the winter of 2013 to 2014 is forecast from lags and the calendar alone. Hourly, not
half hourly. Three months of test is a short year. The households opted in a decade ago.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
