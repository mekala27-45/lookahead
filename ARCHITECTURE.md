# Architecture

```
  SOURCES        EIA-930 six month files (demand, operator forecast, subregions),
                 Open-Meteo hourly weather per authority, Low Carbon London half
                 hourly households, the simulator
        | contracts        typed frames, quarantine rules, provenance, the hierarchy
                           table, the location table            packages/contracts
        | features         point in time: lags at availability, calendar, weather,
                           thresholds                            packages/features
        | forecast         own | gbm, quantiles, conformal; the baselines
                                                                 packages/forecast
        | reconcile        bottom up | top down | MinT; coherence packages/hierarchy
        | events           residuals -> demand event | data defect | none
                                                                 packages/events
        | meter            clusters -> time of use -> bottom up -> reconcile
                                                                 packages/meter
   +----------------------------------------------------------------------------+
   |  EVALUATION (never grades itself)                       packages/evaluation |
   |    rolling origin backtest: point and quantile metrics by authority,       |
   |    horizon and hour, with intervals; skill against the operator with wins  |
   |    and losses; accuracy by level before and after reconciliation; detector |
   |    against planted and known events; the recovery study on the simulator; |
   |    the forecast log scored as actuals arrive                               |
   +-----------------------------------+----------------------------------------+
                                       |
  manifest.json          every metric, interval, curve point, event   packages/registry
        | render          memo, README, RESULTS, cards, callouts      packages/render
   +----------------------------------------------------------------------------+
   |  FLY API      /v1/forecasts (issue, store), /v1/score, /v1/models,         |
   |               /v1/audit, /v1/scorecard, /v1/health          packages/api  |
   |  GITHUB PAGES control room, forecast/[authority], backtest, hierarchy,    |
   |               events, households, report                        web/     |
   +----------------------------------------------------------------------------+
```

## Why the operator's forecast is in every table

It is the only benchmark a hiring manager in this field trusts. It is produced every day by people
with weather forecasts and local knowledge this build does not have, for the same hours, and
published in the same file as the demand. A model that is only compared with the seasonal naive
has been compared with nothing. Losing to the operator in some authorities is the expected honest
result, and the skill table says where; where the published forecast covers a different scope than
the demand series the authority is marked not comparable rather than counted, because a win against
a forecast for a different footprint is not a win.

## Why the harness runs on the simulator first

A rolling origin backtest has a dozen places to leak the future: a lag that reaches past the origin,
a scale computed over the target day, a threshold chosen on the test year, a conformal offset
calibrated on the rows it is scored on, a bootstrap that resamples hours instead of days. The only
way to know it does not is to run it where the truth is known. The simulator gives the harness an
oracle forecaster with a known error and a synthetic operator with a known skill, so the measured
skill has a known true value; it gives the own backend known temperature thresholds and holiday
effects to recover; it gives the reconciliation a truth to be scored against rather than the noisy
actuals; and it gives the detector planted events with known onsets. The recovery study runs all of
that over conditions and seeds, and the missing data condition is where the harness is most likely
to break, which is why it exists.

## The stages and the manifest

Every stage under `packages/registry/src/lookahead_registry/stages` writes one manifest under
`results/manifests/` and `assemble` merges them into `results/manifest.json` in a fixed order.
Every value carries its source, model, population, seeds, condition and as of date, and the
renderer refuses a number that is not in the manifest, so no document and no page prints a figure
a query did not produce. The site reads the same manifest for its callouts and queries the marts,
which the `marts` stage writes from the same results, for its charts.

## The two hierarchies

The grid: the lower 48, the interconnections, EIA's regions, the balancing authorities, and the
eligible subregions plus a remainder node per authority with subregions. The meter: the panel
total over the load shape clusters. Both use the same summing matrix, the same three methods and the
same coherence check, and both publish accuracy before and after at every level.

## The forecast log

Issued forecasts are stored before they are answered: the rows, then the audit row, then the
commit, then the response. Scores are written when actuals arrive and the scorecard reports the
share still unscored, so the live record is the model's real record and not its backtest. The tests
observe every write from a second connection, and CI's out of process script reads the rows back
from a separate process.

## Free tier only

Fly.io for the API (one shared CPU machine that stops when idle, which is why the site probes
twice), Neon Postgres (one project, shared with another build through a schema), GitHub Pages for
the site, GitHub Actions for CI. The data pipeline runs on one machine with two CPUs; the gbm
backend trains on every third origin day for that reason, and says so.
