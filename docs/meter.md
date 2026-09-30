# The meter

**Clustering.** Each household's mean weekday and weekend daily profile at half hour resolution
over 2012-12-01 to 2013-12-01 (the
365 days before the test period), normalized by the
household's mean, clustered by k-means with the number of clusters chosen from
3, 4, 5, 6, 7, 8 by the silhouette score on a validation half of the households
(fit on the even rows of the sorted identifiers, scored on the odd rows). Chosen:
3 clusters (silhouette 0.129) over
5,358 households; shapes are named by rule from the weekday profile.

| Cluster | Shape | Households | Mean kWh per half hour | Share of evening peak | dToU share |
|---:|---|---:|---:|---:|---:|
| 0 | evening peak | 2,502 | 0.206 | 48.8% | 20.2% |
| 1 | evening peak | 2,802 | 0.213 | 50.5% | 20.8% |
| 2 | night heavy | 54 | 0.405 | 0.8% | 0.0% |

Source: real:lcl, 5358 households with a full profile over the year before the test period, as of 2026-09-29.

**The time of use analysis.** The dynamic tariff group was recruited, not randomized; this is an
observational comparison and the plan says so first. The plan is `docs/tou_plan.md`, hashed before
the readings were examined for this question (SHA-256 `b1c595ba7016ae13bf893e84d62b3e83418606b0e52e1b76e5cac9f2bce64c5f`). Matching:
one standard household per dynamic household, same cluster, nearest pre-period mean, without
replacement; 1,088 pairs, 0 dropped. Estimator:
difference in differences per high price event against the same half hours on comparison days,
500 block bootstrap replicates over events, Benjamini-Hochberg across
4 event types. Result: -5.8%
(-7.0% to -4.7%) during
69 events, -0.160 kWh per household per event,
rebound +0.2% in the three hours after.

| Event type | Events | Response | lower | upper | p value | After correction |
|---|---:|---:|---:|---:|---:|---|
| night | 11 | -6.0% | -7.9% | -3.3% | 0.000 | different from zero |
| morning | 15 | -9.4% | -10.6% | -8.0% | 0.000 | different from zero |
| afternoon | 3 | -6.5% | -6.5% | -6.5% | 0.000 | different from zero |
| evening | 40 | -4.8% | -6.0% | -3.4% | 0.000 | different from zero |

Source: real:lcl, 1088 matched pairs over 69 high price events of 2013, 500 seeds, as of 2026-09-29.

**Bottom up and reconciliation.** A fixed panel of 4,485 households
reporting through the whole window, summed hourly per cluster and in total (hourly rather than half
hourly because the forecasting interface is hourly; recorded in `DECISIONS.md`), forecast by the
gbm backend over 2013-12-01 to 2014-02-28 without
weather, and reconciled by bottom up and MinT with the calibration model's validation residuals.

| Level | Method | MAPE | lower | upper | 90 pct coverage |
|---|---|---:|---:|---:|---:|
| panel total | base | 4.30% | 3.76% | 5.05% | 98.6% |
| panel total | bottom_up | 4.27% | 3.73% | 4.92% | 98.9% |
| panel total | mint | 4.26% | 3.73% | 4.89% | 98.8% |
| clusters | base | 6.78% | 5.94% | 7.61% | 97.8% |
| clusters | bottom_up | 6.78% | 5.84% | 7.59% | 97.8% |
| clusters | mint | 9.12% | 7.46% | 10.73% | 92.6% |

Source: real:lcl, model gbm, 4485 households reporting through the whole forecast window, 352 origins, as of 2026-09-29.

**Peak contribution.** Each cluster's evening kilowatts per household and its share of the panel's
weekday evening peak, valued at 60 pounds per kilowatt of
reduction; a program would approach cluster 0
(evening peak) first.

| Cluster | Shape | Households | Evening kW per household | Share of the evening peak | Value of a 10 pct cut, GBP per household |
|---|---|---:|---:|---:|---:|
| 1 | evening peak | 2,802 | 0.58 | 50.5% | 3.5 |
| 0 | evening peak | 2,502 | 0.63 | 48.8% | 3.8 |
| 2 | night heavy | 54 | 0.47 | 0.8% | 2.8 |

Source: real:lcl, model gbm, 4485 households reporting through the whole forecast window, 352 origins, as of 2026-09-29.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
