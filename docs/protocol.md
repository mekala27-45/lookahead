# The forecasting protocol

Origins daily at 0:00 UTC; horizons 1 to 48;
the test period the last 12 months, validation the
12 before, training everything earlier. `own` expands at every
origin (an incremental Gram matrix, one solve per origin); `gbm` refits at the start of every
calendar month of the test year on the previous 1,096 days,
training on every 3 origin days.

**Features at availability.** Ratios to the scale (the mean of the week ending at the origin):
the same hour lag at 24 or 48 hours, the week and two week lags, the origin value, the mean of the
last 24 hours; calendar terms (daily, weekly and yearly Fourier terms, day type, holidays from the
`holidays` package for the United States); heating and cooling degree hours against thresholds
chosen per authority on validation from 8, 10, 12, 14, 16, 18 C (heating) and
16, 18, 20, 22, 24, 26 C (cooling), scaled by the authority's typical demand, and the
change in degree hours against the same hour lag; relative humidity; a missing weather indicator.

**Quantiles.** Levels 0.05, 0.25, 0.50, 0.75, 0.95. `own`: relative conformal residual
quantiles per 6 hour horizon bucket, calibrated on
the validation year's expanding run. `gbm`: five quantile outputs from one booster, conformalized
per bucket on validation. The served levels get the interior test: a level whose empirical
coverage sits at zero or one hundred on validation is degenerate and the page says so.

**Metrics** per authority, horizon and local hour, aggregated with block bootstrap intervals over
test days (7 day blocks, 500
replicates, 90% level) and Benjamini-Hochberg at q 0.05
across authorities in every family.

**Skill against the operator.** Per authority, horizons 1 to 24, the model's MAPE against the
operator's on the same target hours, the paired bootstrap interval and the block sign flip p value;
wins, losses and ties after correction. Authorities are comparable only when the median forecast
to demand ratio sits within 0.90 to
1.10 in both the validation and the test year.

**Sort before any seeded step.** Every draw is taken in a stated order
(`lookahead_core.seeds.rng`), and the manifest is identical under two PYTHONHASHSEED values.

Weather features are observed weather at the target hour, which a real day ahead forecast does not have; the operator's forecast was made with a weather forecast.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
