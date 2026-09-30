# lookahead v0.1.0

Demand forecasting for the U.S. power grid and the household meter, built in one working day
and graded in public against the operator's own day ahead forecast.

- Every balancing authority in the lower 48 that reports demand, 17
  six month EIA-930 files from 2018_Jul_Dec to 2026_Jul_Dec,
  quarantined by named rules; observed weather from Open-Meteo, stated on every figure that uses it.
- Two backends on one interface, `own` (per authority ridge with conformal quantiles) and `gbm`
  (one global XGBoost with quantile objectives), graded by a rolling origin backtest with the
  seasonal naive and the operator in every table. The gbm backend beat the operator in
  18 of 44 comparable
  authorities at horizons 1 to 24 and lost in 17; its
  90 percent bands covered 89.1% of the hours.
- 159 nodes reconciled by bottom up, top down and MinT, coherent to the
  megawatt; helped at bottom_up at the lower 48 level; bottom_up at the interconnection level; bottom_up at the region level; mint at the lower 48 level; mint at the interconnection level; mint at the region level, hurt at top_down at the interconnection level; top_down at the region level; top_down at the authority level; top_down at the subregion level; mint at the authority level; mint at the subregion level.
- A detector that tells demand events from data defects, graded on 5
  known events (3 of 10 rows detected) and on
  planted events by condition.
- The meter: 5,358 London households in 3 load
  shape clusters, a pre-registered time of use analysis (response -5.8%),
  and a cluster forecast reconciled to the panel total.
- A live forecast log on Fly with Neon (https://lookahead-grid-api.fly.dev), verified from a separate
  client, and a control room on GitHub Pages that works from a recorded session when the API is
  asleep. The test server refuses HEAD and answers a first 503, as the hosts do.
- The recovery study on a simulator with known truth (120 runs), the rederive
  in a worktree with every published figure compared, and the eighteen step checklist in
  `RESULTS.md`.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
