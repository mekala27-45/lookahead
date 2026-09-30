# lookahead

Demand forecasting for the U.S. power grid and the household meter: hourly demand for every
balancing authority in the lower 48 with weather, forecast by two backends on one interface out
to 48 hours with calibrated quantiles, graded by a rolling origin backtest against the seasonal
naive and the operator's own day ahead forecast, reconciled across the hierarchy from the lower 48
to the subregion, watched by an anomaly detector that separates demand events from data
defects and is graded on known events, extended to the meter with five and a half thousand London
households clustered by load shape and reconciled bottom up, served by a live API that stores
every forecast it issues and scores it when the actuals arrive, with a registry, model cards, an
operations review rendered from the manifest, and a control room site.

The checklist below marks each of the eighteen mandatory steps done or not done with one line of
evidence per item; the live check in a real browser is the one still open at this render. Every dataset is used in full: 17
balance and 17 subregion files from 2018_Jul_Dec
to 2026_Jul_Dec, every authority that reports demand
(58 of 70;
12 generation only authorities are listed and
excluded by rule), and all 5,566 households of the London release.
Two stated subsamples: the backtest keeps the 51 authorities
with at least 90% clean demand coverage in both the
validation and the test year, and the skill against the operator counts the
44 of them whose published forecast is comparable in scope
(median forecast to demand ratio within 0.90 to
1.10 in both years); the meter forecast uses the
4,485 households that report through its whole window. The weather
the models saw is observed weather, which a real day ahead forecast does not have; every figure
that uses it says so.

The API is live at https://lookahead-grid-api.fly.dev and was verified from a separate client
(AJAY, Windows, PowerShell 5.1.26100.9444): health ok, database
ok, a forecast issued for AECI and its
48 rows and scores read back through the API, audit row
before the response: yes.

Site: https://mekala27-45.github.io/lookahead/ (the control room, one page per authority,
backtest, hierarchy, events, households, report). Memo: `report/operations-review.md`. Results
and the checklist: `RESULTS.md`. Decisions: `DECISIONS.md`. Architecture: `ARCHITECTURE.md`.
Runbook: `docs/runbook.md`.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.

## The two numbers

Over the test year, at horizons 1 to 24, the gbm backend beat the operator's published day
ahead forecast in 18 of 44
comparable balancing authorities (13 to
24 across bootstrap replicates of the test days) and lost
to it in 17 (12 to
22), with 9 ties,
after Benjamini-Hochberg across the authorities. Its 90 percent bands covered
89.1% of the hours they claimed and its 50 percent bands
49.0%. The losses are in the table with the wins.

## What is here

- **The grid, the weather and the meter.** EIA-930 hourly demand, the operator's day ahead
  forecast, net generation and interchange for every balancing authority since
  2018-07-01 05:00:00+00:00, quarantined by named rules (1.113%
  of rows, nothing deleted); Open-Meteo hourly temperature and humidity at one stated location per
  authority; the Low Carbon London release, 167,932,474 half hourly readings from
  5,566 households, read into DuckDB.
- **A simulator with known truth.** 8 authorities in two regions with
  4 subregions, a known temperature response, calendar effects, planted
  events and a synthetic operator forecast whose skill is known, so the harness, the
  reconciliation and the detector were proven on certainty first. The recovery study ran
  120 runs over 6 conditions.
- **Two backends on one interface.** `own`, a per authority ridge regression on Fourier terms,
  heating and cooling degree hours with thresholds chosen on validation, holidays and lags at the
  horizon's availability, with relative conformal quantiles; `gbm`, one global XGBoost over every
  authority with quantile objectives and conformalized intervals, refit monthly. Baselines: the
  seasonal naive at 168 hours and the operator's forecast.
  own MAPE 5.65%, gbm MAPE 5.48%, seasonal naive
  11.66%, operator 13.59% on the paired hours.
- **Reconciliation as a product.** 159 nodes reconciled by bottom up, top
  down and MinT with shrinkage, coherence checked to the megawatt; helped at
  bottom_up at the lower 48 level; bottom_up at the interconnection level; bottom_up at the region level; mint at the lower 48 level; mint at the interconnection level; mint at the region level, hurt at top_down at the interconnection level; top_down at the region level; top_down at the authority level; top_down at the subregion level; mint at the authority level; mint at the subregion level.
- **Events told apart from defects.** A residual detector with a persistence rule and a threshold
  chosen by stated costs, graded on 5 known events
  (3 of 10 rows detected) and on planted
  events by condition.
- **The meter.** 3 load shape clusters, a pre-registered time of use
  analysis (response -5.8% during high price events against matched
  standard households), a cluster forecast reconciled to the panel total, and the peak
  contribution table a demand response program would target from.
- **A forecast log on the live API.** Every forecast issued is stored with its model version and
  origin and scored when actuals arrive; the scorecard reports the share still unscored.

## The skills matrix

| Skill | Where it lives |
|---|---|
| Time series forecasting | `packages/forecast`, the backtest page, notebook 01 |
| Rolling origin backtesting | `packages/evaluation`, `docs/protocol.md` |
| Point in time features, leakage control | `packages/features`, `tests/features`, the registry's leakage gate |
| Probabilistic forecasting and calibration | the quantiles, `packages/forecast/conformal.py`, the reliability diagram |
| Hierarchical forecasting, reconciliation | `packages/hierarchy`, the hierarchy page, notebook 02 |
| Benchmarking against a production forecast | the operator skill table, `packages/registry/stages/skill.py` |
| Weather driven demand modeling | `packages/weather`, the thresholds in `packages/forecast/own.py` |
| Anomaly detection, event classification | `packages/events`, the events page, notebook 03 |
| Simulation and known truth validation | `packages/sim`, the recovery study |
| Clustering and segmentation | `packages/meter/clusters.py`, the load shape clusters |
| Quasi experimental analysis | the time of use analysis, `docs/tou_plan.md` and its hash |
| Gradient boosting at scale | the global gbm backend, `packages/forecast/gbm.py` |
| Statistics | block bootstrap, Benjamini-Hochberg, coverage, `packages/evaluation` |
| Data quality and quarantine | the quarantine rules and report, `packages/contracts` |
| SQL and analytics engineering | the marts, DuckDB in `packages/meter/queries.py`, DuckDB-WASM on the site |
| APIs, persistence, deployment | `packages/api`, `fly.toml`, `scripts/check_persistence.py`, `deploy/` |
| Registry, gates, model cards | `packages/registry/gates.py`, `report/cards/` |
| Visualization | `web/`, the validated palette, the tile map |
| Communication | `report/operations-review.md`, the pushback paragraphs |
| Data licensing and provenance | `data/PROVENANCE.md`, the three declared sources |

## The checklist

| | Item | Status | Evidence |
|---|---|---|---|
| 1 | EIA-930 balance and subregion files ingested in full from 2018_Jul_Dec to the latest, quarantine report published, hierarchy and location tables committed; weather committed with attribution; the London release read in full; provenance and licenses recorded | done | 17 balance and 17 subregion files from 2018_Jul_Dec to 2026_Jul_Dec, 3,877,346 panel rows with 43,156 quarantined (1.113%); `data/hierarchy.csv` (165 nodes), `data/locations.csv`; weather 3,679,344 rows for 51 authorities in `data/weather/`; London 167,932,474 readings from 5,566 households; `data/PROVENANCE.md`. |
| 2 | Simulator with known hierarchy, temperature response, planted events and a synthetic operator; truth tables committed | done | `data/sim/`: 8 authorities over 3 years with 16 planted events and the truth in `truth.json`; the synthetic operator's expected MAPE 2.43%. |
| 3 | Rolling origin harness with the point in time frame and the leakage test; metrics with block bootstrap intervals; Benjamini-Hochberg | done | `packages/evaluation`, `packages/features`; `tests/features` recomputes rows at their origin and refuses the leaky lag; every interval is a 500 replicate block bootstrap; the harness's skill bias on the simulator is -0.1%. |
| 4 | Baselines and the own backend with conformal quantiles; the recovery study on every condition with at least twenty seeds each | done | `own` over 18,615 origins, MAPE 5.65% against the naive's 11.66%; the recovery study ran 120 runs over 6 conditions with 20 seeds each (`results/recovery/`). |
| 5 | The gbm backend with quantile objectives and conformal; the cross check table with both baselines | done | `gbm` (XGBoost, quantile objective at the five levels, conformalized intervals) over 18,615 origins with 13 monthly refits, MAPE 5.48%; the cross check table in `RESULTS.md` (own better in 4, gbm in 40, disagreements on the operator 8). |
| 6 | The skill table against the operator: wins, losses and ties across the authorities with intervals; the two headline numbers | done | gbm beat the operator in 18 of 44 comparable authorities (13 to 24) and lost in 17 (12 to 22); `results/skill/skill_rows.parquet`. |
| 7 | API deployed on Fly with Neon; live URL in the README; verified from a separate client, with the client's response printed | done | https://lookahead-grid-api.fly.dev, checked from AJAY, Windows, PowerShell 5.1.26100.9444 at 2026-09-30T22:21:51.1458679Z: passed yes, 48 rows read back, audit before response yes; `results/deploy/verification.json`. |
| 8 | Forecasts and scores observed from an independent connection; audit before response; the out of process check | done | `tests/api/test_forecast_log.py` (`test_forecast_is_committed`, `test_scores_are_committed`, `test_audit_precedes_response`) and `scripts/check_persistence.py --start-server` in CI. |
| 9 | Quantile coverage and the reliability diagram per horizon; the served levels with their interior test | done | gbm 90 percent coverage 89.1% and 50 percent 49.0% on test, 90.0% on validation; degenerate levels none, interior yes; the reliability table in `RESULTS.md`. |
| 10 | Hierarchy reconciliation by three methods with coherence tests; accuracy by level before and after with intervals | done | 159 nodes, coherence gaps 0.0000 MW (bottom up), 0.0000 MW (top down), 0.0000 MW (MinT); helped at bottom_up at the lower 48 level; bottom_up at the interconnection level; bottom_up at the region level; mint at the lower 48 level; mint at the interconnection level; mint at the region level; hurt at top_down at the interconnection level; top_down at the region level; top_down at the authority level; top_down at the subregion level; mint at the authority level; mint at the subregion level. |
| 11 | Events: detector with its operating point and interior test; recall on the known events table with detection hours; precision and recall on the planted events by condition | done | Threshold 6.0 (interior no); 3 of 10 known event rows detected; on the demonstration grid 6 of 6 defects recovered and 0 called events; by condition in `results/recovery/summary.parquet`. |
| 12 | The meter: clusters with peak shares; the pre-registered time of use analysis with its hash and intervals; the cluster forecast reconciled | done | 3 clusters over 5,358 households; plan hash `b1c595ba7016ae13bf893e84d62b3e83418606b0e52e1b76e5cac9f2bce64c5f`, response -5.8% (-7.0% to -4.7%) over 69 events; MinT at the total helped (4.30% to 4.26%). |
| 13 | Registry gates with a deliberate failure test each; model cards under the contract; the served model chosen by the gates | done | 7 gates in `packages/registry/gates.py` with `tests/registry/test_gates.py`; served: gbm (gbm cleared every gate with the best headline (wins minus losses +1)); cards under `report/cards/`. |
| 14 | Control room, authority, backtest, hierarchy, events, households and report pages live on GitHub Pages, working from the recorded session when the API is asleep; the test server refuses what the host refuses | done | `web/` with the seven routes and one page per authority, `.github/workflows/pages.yml`, `web/public/data/recorded_session.json`; `web/scripts/serve.mjs` refuses HEAD and answers the mock API's first request with a 503; Playwright under `web/tests`. |
| 15 | Latency published; the live check in a real browser recorded in results/live_check.json | not done | Latency measurements on record: 2 (`results/latency/`); live check not checked at not yet in no browser yet, 0 of 0 routes, forecast none. |
| 16 | RESULTS.md with every figure re-derived by the gate, a specific limitations section including the observed weather caveat | done | `RESULTS.md` is rendered from `results/manifest.json` and diffed whole file by `scripts/check_published_numbers.py`; its limitations section opens with the weather caveat. |
| 17 | README with the matrix and this checklist; DECISIONS.md with at least ten dated entries and two reversals; three executed notebooks with a dead end each; the pushback paragraph on every page and in the memo | done | This file; `DECISIONS.md`; `notebooks/` run by nbmake in CI; the paragraph closes every route and the memo. |
| 18 | Coverage at or above 80 percent, mypy strict clean, ruff clean, zero em dashes, zero banned vocabulary, palette validator green including the dark card run, forty to sixty commits, the rederive run in a worktree before the tag, v0.1.0 pushed after the commits, Apache 2.0 for code with the three data sources' terms declared, repo described, topics set | done | `make check` in CI; palette green with 0 failures; `results/rederive.json`; the tag pushed after the last commit. |

Stretch items, never counted toward the checklist: the refresh job (not done), forecast weather
in place of observed weather (not done), a neural backend (not done), the published benchmark
comparison (not done), the models, explore and simulator pages (not done), the containers in CI
(Dockerfile.api is built by the deploy; a pipeline container is not done).

## Running it

`make data` reads the EIA files, the weather cache and the London release from
`data/external/` (the Makefile prints the paths and the download commands); `make pipeline` runs
every stage in order and writes `results/manifest.json`; `make render` renders every document from
it; `make check` runs the gates, lint, types and tests; `make rederive` reruns the pipeline in a
worktree and compares the manifests. The API runs with `uvicorn lookahead_api.main:app` against
`DATABASE_URL`; `deploy/deploy.ps1` deploys it to Fly from a Windows machine and
`deploy/verify.ps1` checks it from there. Writes to the API need the token; this is a
demonstration, and the statement on every surface says so.

## License

Code under Apache 2.0 (`LICENSE`). Demand data from the U.S. Energy Information Administration
is U.S. government work in the public domain; weather from Open-Meteo is CC BY 4.0; the Low
Carbon London household data from UK Power Networks is CC BY 4.0 and is never committed raw.
`data/PROVENANCE.md` names every file.
