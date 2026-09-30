# Definitions

A policy, not a glossary: what counts, and why. Every constant is quoted from
`lookahead_core.config.POLICY` through the manifest, and a test holds the documents to the code.

**Demand.** EIA-930's hourly demand for a balancing authority in megawatts, the raw value kept
in `demand_raw` and the clean value nulled where a quarantine rule fired
(`lookahead_contracts.quarantine`). **The operator forecast** is the day ahead demand forecast
published in the same file by the same authority.

**The origin and the issue time.** One origin per authority per day at
0:00 UTC, the evening before in every U.S. time zone, which is when a
day ahead process issues. **A horizon** is an hour after the origin, 1 to 48.
**Availability of a lag at an origin**: a value is available only if its hour is at or before the
origin; the same hour lag is therefore 24 hours for horizons 1 to 24 and 48 for 25 to 48
(`lookahead_features.build.same_hour_lag`), and `PointInTimeFrame` refuses any read after the
origin with a `LeakageError`.

**A test day** is a day of the last 12 months
(2025-09-29 to 2026-09-28); **validation** is the
12 months before (2024-09-29 on);
training is everything from 2018-07-01. Every choice (thresholds,
penalty, conformal offsets, served levels) is made on validation and reported on test; asking the
code to choose on test raises `ProtocolError`.

**Seasonal naive.** Demand at the same hour 168 hours earlier,
falling back to the next available week when that hour is missing (`lookahead_forecast.baselines`).

**MAPE.** The mean over rows of the absolute error divided by the actual, on rows with a positive
actual and a finite median. **MASE** divides the mean absolute error by the seasonal naive's. **Skill
score** against the operator: one minus the model's MAPE over the operator's MAPE on the same target
hours, per authority, with a paired block bootstrap interval and a block sign flip p value.
**Pinball loss at a level q**: q times the shortfall when the actual exceeds the quantile, (1 minus
q) times the excess otherwise. **CRPS** is the trapezoid integral of twice the pinball loss over the
served levels, relative to the actual. **Coverage** is the share of actuals inside the interval
between the paired levels (0.25 to 0.75 for 50 percent, 0.05 to 0.95 for 90 percent).

**The daily peak and its timing error.** The hour of the day's largest actual against the hour of
the largest median forecast, in hours; the peak error is the absolute error of the forecast at the
actual peak hour as a share of it. **The morning and evening ramps** are the change from 05:00 to
09:00 and from 16:00 to 20:00 local time, and their error is the absolute error of the forecast
change.

**Coherence.** Every node's forecast equals the sum of its leaves within floating tolerance
(`lookahead_hierarchy.summing.check_coherent`).

**A demand event** is a run of at least 3 consecutive hours
whose standardized short horizon residual passes the threshold and whose raw values were not
flagged by a quarantine rule; **a data defect** is a run of hours a quarantine rule flagged (zero,
negative, duplicated, missing, spike) with normal neighbors. A dead feed is never a demand event.

**A load shape cluster** is a k-means cluster of households by their normalized mean weekday and
weekend half hourly profile over the 365 days before the
meter's test period, the count chosen by the silhouette on a validation half of the households.

**The time of use high price event** is a maximal run of consecutive half hours whose tariff band
is High in the 2013 dynamic schedule.

**A forecast log entry** is one row of the API's `forecasts` table: the authority, the origin, the
model version, the spec hash, the data source, 48 rows of quantiles, and the audit row written
before the response.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
