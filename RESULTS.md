# Results

Rendered from `results/manifest.json` (as of 2026-09-29, demonstration seed
13); `scripts/check_published_numbers.py` re-renders this file and fails CI if
it differs. Stages present in the manifest: data, weather, simulate, recovery, backtest_own, backtest_gbm, skill, hierarchy, events, meter, registry, latency. Every table names
its source, model, population, seed count and condition in the line beneath it. The served
backend is gbm.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.

## The checklist (Section 20 of the brief)

| | Item | Status | Evidence |
|---|---|---|---|
| 1 | EIA-930 balance and subregion files ingested in full from 2018_Jul_Dec to the latest, quarantine report published, hierarchy and location tables committed; weather committed with attribution; the London release read in full; provenance and licenses recorded | done | 17 balance and 17 subregion files from 2018_Jul_Dec to 2026_Jul_Dec, 3,877,346 panel rows with 43,156 quarantined (1.113%); `data/hierarchy.csv` (165 nodes), `data/locations.csv`; weather 3,679,344 rows for 51 authorities in `data/weather/`; London 167,932,474 readings from 5,566 households; `data/PROVENANCE.md`. |
| 2 | Simulator with known hierarchy, temperature response, planted events and a synthetic operator; truth tables committed | done | `data/sim/`: 8 authorities over 3 years with 16 planted events and the truth in `truth.json`; the synthetic operator's expected MAPE 2.43%. |
| 3 | Rolling origin harness with the point in time frame and the leakage test; metrics with block bootstrap intervals; Benjamini-Hochberg | done | `packages/evaluation`, `packages/features`; `tests/features` recomputes rows at their origin and refuses the leaky lag; every interval is a 500 replicate block bootstrap; the harness's skill bias on the simulator is -0.1%. |
| 4 | Baselines and the own backend with conformal quantiles; the recovery study on every condition with at least twenty seeds each | done | `own` over 18,615 origins, MAPE 5.65% against the naive's 11.66%; the recovery study ran 120 runs over 6 conditions with 20 seeds each (`results/recovery/`). |
| 5 | The gbm backend with quantile objectives and conformal; the cross check table with both baselines | done | `gbm` (XGBoost, quantile objective at the five levels, conformalized intervals) over 18,615 origins with 13 monthly refits, MAPE 5.48%; the cross check table in `RESULTS.md` (own better in 4, gbm in 40, disagreements on the operator 8). |
| 6 | The skill table against the operator: wins, losses and ties across the authorities with intervals; the two headline numbers | done | gbm beat the operator in 18 of 44 comparable authorities (13 to 24) and lost in 17 (12 to 22); `results/skill/skill_rows.parquet`. |
| 7 | API deployed on Fly with Neon; live URL in the README; verified from a separate client, with the client's response printed | done | https://lookahead-grid-api.fly.dev, checked from AJAY, Windows, PowerShell 5.1.26100.9444 at 2026-09-29T23:59:24.0034369Z: passed yes, 48 rows read back, audit before response yes; `results/deploy/verification.json`. |
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

Stretch items, never counted: the refresh job (not done); forecast weather in place of observed
weather (not done); a neural backend (not done); the published benchmark comparison (not done);
the models, explore and simulator pages (not done); the pipeline container in CI (not done; Fly
builds `Dockerfile.api` on deploy).

## The two headline numbers

| | gbm, horizons 1 to 24 | Interval |
|---|---:|---:|
| Authorities where the model beat the operator | 18 of 44 | 13 to 24 |
| Authorities where the operator beat the model | 17 of 44 | 12 to 22 |
| Ties after correction | 9 | |
| Pooled MAPE, model against operator | 4.52% against 5.52% | skill +18.1% |
| 90 percent coverage on test | 89.1% | 88.6% to 89.6% |
| 50 percent coverage on test | 49.0% | 48.3% to 49.7% |

Source: real:eia930, model gbm, 44 authorities with a comparable operator forecast, test year, as of 2026-09-29.

The 7 authorities whose published forecast is not
comparable in scope are never counted: FMPP (forecast to demand 1.01 validation, 0.76 test), FPC (forecast to demand 0.76 validation, 0.76 test), GVL (forecast to demand 0.91 validation, 0.89 test), PSCO (forecast to demand 0.94 validation, 0.83 test), PSEI (forecast to demand 0.72 validation, 0.53 test), SPA (forecast to demand 2.04 validation, 1.06 test), SWPP (forecast to demand 1.01 validation, 1.11 test).

| Authority | Validation median ratio | Test median ratio | Why |
|---|---:|---:|---|
| FMPP | 1.01 | 0.76 | the published forecast covers a different scope than the demand series |
| FPC | 0.76 | 0.76 | the published forecast covers a different scope than the demand series |
| GVL | 0.91 | 0.89 | the published forecast covers a different scope than the demand series |
| PSCO | 0.94 | 0.83 | the published forecast covers a different scope than the demand series |
| PSEI | 0.72 | 0.53 | the published forecast covers a different scope than the demand series |
| SPA | 2.04 | 1.06 | the published forecast covers a different scope than the demand series |
| SWPP | 1.01 | 1.11 | the published forecast covers a different scope than the demand series |

Source: real:eia930, model both, authorities in the backtest, test year, as of 2026-09-29.

## The skill table against the operator

Horizons 1 to 24, the headline band; skill is one minus the model's MAPE over the operator's on
the same target hours, with the paired block bootstrap interval and the Benjamini-Hochberg
verdict.

| Authority | Hours | Model MAPE | Operator MAPE | Skill | lower | upper | p value | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| AECI | 8,760 | 5.08% | 1.97% | -157.9% | -186.3% | -134.9% | 0.002 | loss |
| AVA | 8,734 | 2.49% | 1.65% | -50.6% | -58.2% | -41.3% | 0.002 | loss |
| AZPS | 8,745 | 4.45% | 9.73% | +54.3% | +50.3% | +58.2% | 0.002 | win |
| BANC | 8,650 | 3.37% | 3.49% | +3.6% | -28.0% | +31.2% | 1.000 | tie |
| BPAT | 8,760 | 2.22% | 1.85% | -20.5% | -28.8% | -12.3% | 0.002 | loss |
| CHPD | 8,760 | 3.62% | 3.09% | -17.1% | -23.8% | -10.0% | 0.002 | loss |
| CISO | 8,658 | 3.04% | 8.97% | +66.1% | +64.0% | +68.2% | 0.002 | win |
| CPLE | 8,255 | 4.30% | 3.79% | -13.3% | -22.8% | -3.0% | 0.028 | loss |
| CPLW | 8,135 | 4.02% | 4.22% | +4.6% | -5.1% | +14.4% | 0.523 | tie |
| DOPD | 8,760 | 2.75% | 4.72% | +41.7% | +35.2% | +47.2% | 0.002 | win |
| DUK | 8,711 | 3.45% | 3.65% | +5.5% | -12.9% | +21.4% | 0.651 | tie |
| EPE | 8,660 | 3.67% | 3.20% | -14.7% | -21.3% | -6.1% | 0.002 | loss |
| ERCO | 8,688 | 2.78% | 1.99% | -39.2% | -52.4% | -26.3% | 0.002 | loss |
| FPL | 8,733 | 3.94% | 3.38% | -16.8% | -25.6% | -9.1% | 0.002 | loss |
| GCPD | 8,721 | 1.80% | 2.29% | +21.5% | +10.4% | +29.5% | 0.004 | win |
| HST | 8,734 | 5.21% | 6.75% | +22.8% | +19.5% | +27.2% | 0.002 | win |
| IID | 8,614 | 4.83% | 3.44% | -40.2% | -51.7% | -29.1% | 0.002 | loss |
| IPCO | 8,760 | 2.78% | 5.26% | +47.1% | +39.9% | +52.8% | 0.002 | win |
| ISNE | 8,759 | 5.52% | 3.04% | -81.7% | -90.9% | -71.5% | 0.002 | loss |
| JEA | 8,760 | 4.10% | 4.45% | +7.7% | +1.1% | +15.2% | 0.076 | tie |
| LDWP | 8,710 | 29.98% | 36.42% | +17.7% | +6.5% | +37.0% | 0.002 | win |
| LGEE | 8,744 | 4.12% | 8.14% | +49.4% | +45.2% | +53.1% | 0.002 | win |
| MISO | 8,722 | 2.34% | 2.65% | +11.5% | +4.7% | +17.3% | 0.004 | win |
| NEVP | 8,745 | 2.78% | 8.93% | +68.8% | +66.0% | +71.4% | 0.002 | win |
| NWMT | 8,753 | 3.12% | 2.55% | -22.4% | -33.3% | -11.6% | 0.002 | loss |
| NYIS | 8,731 | 3.75% | 2.63% | -42.2% | -53.2% | -30.7% | 0.002 | loss |
| PACE | 8,664 | 3.15% | 5.22% | +39.6% | +34.3% | +44.5% | 0.002 | win |
| PACW | 8,760 | 2.61% | 2.68% | +2.7% | -5.6% | +11.3% | 0.573 | tie |
| PGE | 8,760 | 2.55% | 1.58% | -61.6% | -72.0% | -53.1% | 0.002 | loss |
| PJM | 8,712 | 2.99% | 3.50% | +14.7% | +8.9% | +19.6% | 0.002 | win |
| PNM | 8,760 | 2.95% | 5.64% | +47.6% | +44.3% | +51.5% | 0.002 | win |
| SC | 8,565 | 4.33% | 4.01% | -7.9% | -15.9% | +0.8% | 0.124 | tie |
| SCEG | 8,255 | 4.91% | 5.66% | +13.3% | +7.2% | +20.0% | 0.002 | win |
| SCL | 8,760 | 3.08% | 3.40% | +9.4% | +4.5% | +14.7% | 0.014 | win |
| SEC | 8,542 | 11.84% | 15.34% | +22.9% | +11.5% | +33.1% | 0.006 | win |
| SOCO | 8,758 | 2.99% | 1.38% | -117.4% | -148.5% | -99.5% | 0.002 | loss |
| SRP | 8,760 | 7.18% | 9.68% | +25.9% | +17.3% | +32.3% | 0.002 | win |
| TAL | 8,759 | 4.46% | 4.26% | -4.8% | -10.6% | +2.4% | 0.200 | tie |
| TEC | 8,758 | 3.90% | 4.00% | +2.6% | -1.9% | +8.2% | 0.429 | tie |
| TEPC | 8,712 | 3.67% | 2.87% | -27.7% | -33.8% | -20.3% | 0.002 | loss |
| TIDC | 8,719 | 3.27% | 3.18% | -2.8% | -10.5% | +3.1% | 0.477 | tie |
| TPWR | 8,760 | 3.01% | 2.29% | -31.5% | -38.5% | -22.4% | 0.002 | loss |
| TVA | 8,755 | 3.43% | 2.33% | -46.8% | -60.4% | -34.0% | 0.002 | loss |
| WALC | 8,732 | 9.30% | 23.56% | +60.5% | +52.5% | +66.3% | 0.002 | win |

Source: real:eia930, model gbm, 44 authorities with a comparable operator forecast, test year, as of 2026-09-29.

Horizons 25 to 48: wins 11, losses
28, ties 5; the target
day: wins 13, losses
20, ties 11.

| Authority | Hours | Model MAPE | Operator MAPE | Skill | lower | upper | p value | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| AECI | 8,712 | 5.46% | 1.97% | -177.5% | -209.9% | -149.7% | 0.002 | loss |
| AVA | 8,686 | 2.70% | 1.65% | -63.2% | -73.2% | -52.6% | 0.002 | loss |
| AZPS | 8,745 | 4.66% | 9.73% | +52.1% | +48.0% | +56.2% | 0.002 | win |
| BANC | 8,603 | 3.66% | 3.49% | -4.6% | -40.5% | +27.4% | 0.996 | tie |
| BPAT | 8,712 | 2.45% | 1.84% | -32.8% | -40.6% | -24.6% | 0.002 | loss |
| CHPD | 8,712 | 3.97% | 3.09% | -28.5% | -36.4% | -20.5% | 0.002 | loss |
| CISO | 8,658 | 3.41% | 8.97% | +62.0% | +59.4% | +64.4% | 0.002 | win |
| CPLE | 8,232 | 4.63% | 3.79% | -22.2% | -32.7% | -10.4% | 0.002 | loss |
| CPLW | 8,112 | 4.29% | 4.22% | -1.7% | -12.6% | +9.3% | 0.800 | tie |
| DOPD | 8,712 | 3.00% | 4.69% | +35.9% | +28.4% | +42.3% | 0.002 | win |
| DUK | 8,688 | 3.74% | 3.65% | -2.4% | -20.2% | +17.4% | 0.880 | tie |
| EPE | 8,660 | 3.89% | 3.20% | -21.5% | -28.3% | -13.1% | 0.002 | loss |
| ERCO | 8,640 | 3.04% | 1.98% | -53.0% | -67.8% | -39.7% | 0.002 | loss |
| FPL | 8,711 | 4.21% | 3.37% | -24.7% | -34.0% | -16.8% | 0.002 | loss |
| GCPD | 8,674 | 2.02% | 2.31% | +12.2% | 0.0% | +20.8% | 0.100 | tie |
| HST | 8,687 | 5.58% | 6.74% | +17.2% | +13.1% | +22.0% | 0.002 | win |
| IID | 8,568 | 5.24% | 3.43% | -52.8% | -63.9% | -40.6% | 0.002 | loss |
| IPCO | 8,712 | 3.14% | 5.26% | +40.4% | +31.8% | +46.7% | 0.002 | win |
| ISNE | 8,711 | 5.73% | 3.03% | -88.8% | -98.6% | -76.8% | 0.002 | loss |
| JEA | 8,712 | 4.42% | 4.45% | +0.6% | -5.8% | +9.7% | 0.902 | tie |
| LDWP | 8,664 | 31.87% | 36.56% | +12.8% | +3.0% | +35.2% | 0.022 | win |
| LGEE | 8,744 | 4.44% | 8.14% | +45.4% | +41.2% | +49.4% | 0.002 | win |
| MISO | 8,722 | 2.54% | 2.65% | +3.9% | -2.9% | +10.9% | 0.413 | tie |
| NEVP | 8,697 | 3.05% | 8.94% | +65.8% | +62.5% | +69.2% | 0.002 | win |
| NWMT | 8,705 | 3.32% | 2.55% | -30.5% | -41.7% | -19.9% | 0.002 | loss |
| NYIS | 8,683 | 3.92% | 2.63% | -48.7% | -59.6% | -36.6% | 0.002 | loss |
| PACE | 8,616 | 3.30% | 5.23% | +36.8% | +31.7% | +41.7% | 0.002 | win |
| PACW | 8,712 | 2.86% | 2.68% | -6.8% | -17.1% | +3.1% | 0.287 | tie |
| PGE | 8,712 | 2.75% | 1.57% | -74.5% | -86.3% | -64.6% | 0.002 | loss |
| PJM | 8,712 | 3.23% | 3.50% | +7.7% | +0.5% | +14.1% | 0.076 | tie |
| PNM | 8,760 | 3.07% | 5.64% | +45.6% | +41.9% | +48.6% | 0.002 | win |
| SC | 8,520 | 4.59% | 4.00% | -14.8% | -24.1% | -6.3% | 0.008 | loss |
| SCEG | 8,208 | 4.46% | 5.00% | +10.8% | +3.1% | +18.1% | 0.044 | tie |
| SCL | 8,712 | 3.33% | 3.39% | +1.9% | -3.5% | +8.4% | 0.633 | tie |
| SEC | 8,542 | 12.39% | 15.34% | +19.2% | +7.0% | +28.9% | 0.018 | win |
| SOCO | 8,711 | 3.25% | 1.38% | -135.2% | -164.8% | -113.3% | 0.002 | loss |
| SRP | 8,760 | 7.63% | 9.73% | +21.6% | +12.8% | +29.1% | 0.002 | win |
| TAL | 8,712 | 4.76% | 4.27% | -11.5% | -17.1% | -3.8% | 0.008 | loss |
| TEC | 8,711 | 4.18% | 4.01% | -4.5% | -10.1% | +2.2% | 0.246 | tie |
| TEPC | 8,712 | 3.87% | 2.87% | -34.8% | -40.8% | -25.7% | 0.002 | loss |
| TIDC | 8,672 | 3.67% | 3.19% | -15.0% | -22.6% | -7.2% | 0.004 | loss |
| TPWR | 8,712 | 3.33% | 2.28% | -46.1% | -55.7% | -36.3% | 0.002 | loss |
| TVA | 8,707 | 3.71% | 2.33% | -59.3% | -74.6% | -44.3% | 0.002 | loss |
| WALC | 8,732 | 9.79% | 23.57% | +58.4% | +49.6% | +65.1% | 0.002 | win |

Source: real:eia930, model gbm, 44 authorities with a comparable operator forecast, test year, as of 2026-09-29.

## The cross check: own against gbm, both baselines beside them

own has the lower error in 4 authorities and gbm in
40; the two fall on different sides of the operator in
8 of 44. Where they
disagree the table says so; nothing is averaged.

| Authority | own MAPE | gbm MAPE | Seasonal naive MAPE | Operator MAPE | Lower error | Disagree on the operator |
|---|---:|---:|---:|---:|---|---|
| AECI | 5.11% | 5.08% | 18.23% | 1.97% | gbm | no |
| AVA | 2.87% | 2.49% | 7.24% | 1.65% | gbm | no |
| AZPS | 4.60% | 4.45% | 9.64% | 9.73% | gbm | no |
| BANC | 4.23% | 3.36% | 9.36% | 3.49% | gbm | yes |
| BPAT | 2.52% | 2.22% | 5.94% | 1.85% | gbm | no |
| CHPD | 3.71% | 3.62% | 10.45% | 3.09% | gbm | no |
| CISO | 3.83% | 3.07% | 6.74% | 8.97% | gbm | no |
| CPLE | 4.85% | 4.47% | 15.75% | 3.79% | gbm | no |
| CPLW | 4.45% | 4.12% | 14.89% | 4.22% | gbm | yes |
| DOPD | 2.86% | 2.75% | 7.67% | 4.72% | gbm | no |
| DUK | 4.22% | 3.48% | 12.92% | 3.65% | gbm | yes |
| EPE | 4.22% | 3.71% | 9.39% | 3.20% | gbm | no |
| ERCO | 2.99% | 2.78% | 7.43% | 1.99% | gbm | no |
| FPL | 4.35% | 3.94% | 9.96% | 3.38% | gbm | no |
| GCPD | 1.97% | 1.80% | 4.83% | 2.29% | gbm | no |
| HST | 5.25% | 5.21% | 12.60% | 6.75% | gbm | no |
| IID | 5.36% | 4.82% | 13.59% | 3.44% | gbm | no |
| IPCO | 3.02% | 2.78% | 7.79% | 5.26% | gbm | no |
| ISNE | 5.52% | 5.52% | 11.06% | 3.04% | own | no |
| JEA | 4.50% | 4.10% | 12.85% | 4.45% | gbm | yes |
| LDWP | 25.09% | 29.84% | 42.14% | 36.42% | own | no |
| LGEE | 4.47% | 4.12% | 13.41% | 8.14% | gbm | no |
| MISO | 2.76% | 2.35% | 7.30% | 2.65% | gbm | yes |
| NEVP | 2.99% | 2.78% | 8.63% | 8.93% | gbm | no |
| NWMT | 3.24% | 3.12% | 7.03% | 2.55% | gbm | no |
| NYIS | 4.36% | 3.75% | 9.32% | 2.63% | gbm | no |
| PACE | 3.32% | 3.14% | 6.53% | 5.22% | gbm | no |
| PACW | 3.23% | 2.61% | 6.76% | 2.68% | gbm | yes |
| PGE | 3.21% | 2.55% | 6.29% | 1.58% | gbm | no |
| PJM | 3.29% | 2.99% | 8.72% | 3.50% | gbm | no |
| PNM | 3.00% | 2.95% | 6.11% | 5.64% | gbm | no |
| SC | 4.56% | 4.39% | 12.08% | 4.01% | gbm | no |
| SCEG | 5.14% | 4.92% | 13.55% | 5.66% | gbm | no |
| SCL | 3.45% | 3.08% | 7.12% | 3.40% | gbm | yes |
| SEC | 12.11% | 11.88% | 23.00% | 15.34% | gbm | no |
| SOCO | 3.37% | 2.99% | 10.95% | 1.38% | gbm | no |
| SRP | 7.06% | 7.18% | 13.91% | 9.68% | own | no |
| TAL | 4.83% | 4.46% | 13.80% | 4.26% | gbm | no |
| TEC | 4.27% | 3.90% | 11.62% | 4.00% | gbm | yes |
| TEPC | 3.89% | 3.67% | 9.21% | 2.87% | gbm | no |
| TIDC | 4.19% | 3.27% | 8.50% | 3.18% | gbm | no |
| TPWR | 3.29% | 3.01% | 8.61% | 2.29% | gbm | no |
| TVA | 3.87% | 3.43% | 12.27% | 2.33% | gbm | no |
| WALC | 8.98% | 9.31% | 17.33% | 23.56% | own | no |

Source: real:eia930, model both, authorities in the backtest, test year, as of 2026-09-29.

## The backtest by backend

| | own | gbm | Seasonal naive | Operator (paired hours) |
|---|---:|---:|---:|---:|
| MAPE, all horizons | 5.65% (5.25% to 6.07%) | 5.48% (5.01% to 5.98%) | 11.66% | 13.59% |
| MASE against the weekly naive | 0.426 | 0.404 | | |
| CRPS, relative | 3.89% | 3.80% | | |
| 90 percent coverage | 88.3% | 89.1% | | |
| 50 percent coverage | 48.4% | 49.0% | | |
| Validation coverage, 90 percent | 90.1% | 90.0% | | |
| Daily peak error | 4.88% | 4.83% | 11.93% | 103.78% |
| Median peak timing error | 1.0 h h | 1.0 h h | | 1.0 h h |
| Morning ramp error | 3.43% | 3.36% | | 4.18% |
| Evening ramp error | 4.34% | 4.38% | | 4.07% |
| Origins, fits, run time | 18,615, 18,615, 332.8 s | 18,615, 14, 4,356.0 s | | |
| Throughput, origins a minute on CPU | 3,356.3 | 256.4 | | |

Source: real:eia930, model own, 51 authorities in the backtest, test year, as of 2026-09-29. Source: real:eia930, model gbm, 51 authorities in the backtest, test year, as of 2026-09-29.

Weather features are observed weather at the target hour, which a real day ahead forecast does not have; the operator's forecast was made with a weather forecast.

### By horizon, gbm

| Horizon (h) | MAPE | Operator MAPE | Seasonal naive MAPE | CRPS | 50 pct coverage | 90 pct coverage |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 4.04% | 7.60% | 11.90% | 2.81% | 50.3% | 89.7% |
| 2 | 4.07% | 7.63% | 11.51% | 2.83% | 47.4% | 88.6% |
| 3 | 4.05% | 7.46% | 11.15% | 2.80% | 48.5% | 88.6% |
| 4 | 4.51% | 7.90% | 11.45% | 3.17% | 48.6% | 89.3% |
| 5 | 4.27% | 7.17% | 11.05% | 2.95% | 49.1% | 90.1% |
| 6 | 4.42% | 58.89% | 11.20% | 3.07% | 49.0% | 90.4% |
| 7 | 4.76% | 8.23% | 11.46% | 3.36% | 52.0% | 91.1% |
| 8 | 4.38% | 49.21% | 11.01% | 3.01% | 50.7% | 90.6% |
| 9 | 4.59% | 50.31% | 11.18% | 3.16% | 49.6% | 90.0% |
| 10 | 4.67% | 6.71% | 11.19% | 3.21% | 48.7% | 89.6% |
| 11 | 4.76% | 6.86% | 11.07% | 3.28% | 48.6% | 90.1% |
| 12 | 4.79% | 7.24% | 10.90% | 3.31% | 49.0% | 89.7% |
| 13 | 4.95% | 7.04% | 10.98% | 3.46% | 47.8% | 90.0% |
| 14 | 4.98% | 7.34% | 11.04% | 3.46% | 49.6% | 89.8% |
| 15 | 5.24% | 7.90% | 11.15% | 3.65% | 49.7% | 89.4% |
| 16 | 5.28% | 8.65% | 11.30% | 3.67% | 48.1% | 89.0% |
| 17 | 5.38% | 8.55% | 11.52% | 3.73% | 48.3% | 88.1% |
| 18 | 5.66% | 8.94% | 12.15% | 3.93% | 47.6% | 87.7% |
| 19 | 5.70% | 9.01% | 12.36% | 3.95% | 49.2% | 89.3% |
| 20 | 5.88% | 9.73% | 12.91% | 4.09% | 48.8% | 88.7% |
| 21 | 5.87% | 9.08% | 13.04% | 4.07% | 48.3% | 88.8% |
| 22 | 5.74% | 9.35% | 12.98% | 3.98% | 48.2% | 88.4% |
| 23 | 5.65% | 8.48% | 12.84% | 3.93% | 48.6% | 88.9% |
| 24 | 5.36% | 7.96% | 12.32% | 3.73% | 49.2% | 88.7% |
| 25 | 5.51% | 7.61% | 11.92% | 3.84% | 49.6% | 88.7% |
| 26 | 5.44% | 7.64% | 11.53% | 3.79% | 48.8% | 88.4% |
| 27 | 5.29% | 7.47% | 11.17% | 3.68% | 49.1% | 88.6% |
| 28 | 5.74% | 7.90% | 11.47% | 4.03% | 48.8% | 88.9% |
| 29 | 5.45% | 7.18% | 11.06% | 3.76% | 48.6% | 89.4% |
| 30 | 5.63% | 58.97% | 11.20% | 3.91% | 48.7% | 89.7% |
| 31 | 5.91% | 8.24% | 11.46% | 4.14% | 50.6% | 89.7% |
| 32 | 5.45% | 49.34% | 11.03% | 3.75% | 50.4% | 89.4% |
| 33 | 5.62% | 50.44% | 11.19% | 3.88% | 49.9% | 89.3% |
| 34 | 5.65% | 6.71% | 11.20% | 3.90% | 50.1% | 89.3% |
| 35 | 5.70% | 6.86% | 11.08% | 3.94% | 50.1% | 89.2% |
| 36 | 5.72% | 7.23% | 10.91% | 3.95% | 50.1% | 89.3% |
| 37 | 5.86% | 7.05% | 11.00% | 4.10% | 49.0% | 89.7% |
| 38 | 5.91% | 7.35% | 11.05% | 4.11% | 49.2% | 89.3% |
| 39 | 6.23% | 7.91% | 11.17% | 4.33% | 48.7% | 88.6% |
| 40 | 6.26% | 8.66% | 11.31% | 4.36% | 47.7% | 87.9% |
| 41 | 6.35% | 8.55% | 11.53% | 4.40% | 47.7% | 87.9% |
| 42 | 6.62% | 8.95% | 12.17% | 4.60% | 47.6% | 87.4% |
| 43 | 6.64% | 9.01% | 12.37% | 4.60% | 48.4% | 89.0% |
| 44 | 6.80% | 9.74% | 12.91% | 4.73% | 48.1% | 88.4% |
| 45 | 6.78% | 9.09% | 13.05% | 4.70% | 48.3% | 88.3% |
| 46 | 6.62% | 9.36% | 12.98% | 4.60% | 48.4% | 88.4% |
| 47 | 6.49% | 8.49% | 12.84% | 4.52% | 48.6% | 88.5% |
| 48 | 6.23% | 7.97% | 12.32% | 4.32% | 48.2% | 88.5% |

Source: real:eia930, model gbm, 51 authorities in the backtest, test year, as of 2026-09-29.

### By authority, gbm

| Authority | Hours | MAPE | lower | upper | Operator MAPE | Seasonal naive MAPE | MASE | CRPS | 50 pct coverage | 90 pct coverage |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AECI | 17,501 | 5.75% | 5.42% | 6.24% | 1.97% | 18.24% | 0.310 | 3.89% | 48.3% | 87.2% |
| AVA | 17,499 | 2.79% | 2.64% | 2.95% | 1.65% | 7.24% | 0.380 | 1.89% | 52.0% | 92.0% |
| AZPS | 17,473 | 4.82% | 4.52% | 5.02% | 9.73% | 9.64% | 0.481 | 3.24% | 43.2% | 86.0% |
| BANC | 17,466 | 3.82% | 3.57% | 4.05% | 3.50% | 9.34% | 0.401 | 2.63% | 51.4% | 90.5% |
| BPAT | 17,503 | 2.57% | 2.43% | 2.72% | 1.85% | 5.95% | 0.426 | 1.73% | 50.8% | 93.8% |
| CHPD | 17,503 | 4.13% | 3.79% | 4.57% | 3.09% | 10.46% | 0.394 | 2.79% | 50.0% | 91.1% |
| CISO | 17,395 | 3.59% | 3.40% | 3.81% | 8.97% | 6.74% | 0.517 | 2.41% | 51.3% | 92.2% |
| CPLE | 17,450 | 5.19% | 4.78% | 5.59% | 3.79% | 15.76% | 0.325 | 3.53% | 49.2% | 88.6% |
| CPLW | 17,450 | 4.81% | 4.40% | 5.23% | 4.22% | 14.91% | 0.319 | 3.27% | 49.8% | 89.0% |
| DOPD | 17,503 | 3.13% | 2.97% | 3.32% | 4.71% | 7.67% | 0.412 | 2.12% | 50.7% | 91.0% |
| DUK | 17,450 | 4.06% | 3.74% | 4.34% | 3.65% | 12.92% | 0.309 | 2.77% | 49.3% | 88.9% |
| EPE | 17,399 | 4.07% | 3.74% | 4.35% | 3.20% | 9.37% | 0.427 | 2.77% | 52.0% | 90.2% |
| ERCO | 17,405 | 3.20% | 2.95% | 3.44% | 1.99% | 7.41% | 0.441 | 2.14% | 50.9% | 91.8% |
| FMPP | 17,476 | 4.55% | 3.97% | 5.24% | 18.87% | 11.03% | 0.409 | 3.15% | 48.0% | 89.7% |
| FPC | 17,450 | 5.18% | 4.76% | 5.64% | 23.98% | 12.88% | 0.412 | 3.49% | 50.1% | 89.0% |
| FPL | 17,494 | 4.50% | 3.97% | 5.20% | 3.38% | 9.97% | 0.447 | 3.08% | 51.3% | 91.0% |
| GCPD | 17,501 | 2.11% | 1.99% | 2.28% | 2.30% | 4.83% | 0.436 | 1.45% | 52.6% | 96.3% |
| GVL | 16,992 | 5.30% | 4.95% | 5.59% | 11.46% | 13.27% | 0.409 | 3.55% | 47.3% | 87.4% |
| HST | 17,498 | 5.94% | 5.59% | 6.29% | 6.75% | 12.62% | 0.487 | 3.94% | 48.0% | 88.3% |
| IID | 17,307 | 5.43% | 4.94% | 5.93% | 3.44% | 13.60% | 0.376 | 3.65% | 48.7% | 88.6% |
| IPCO | 17,503 | 3.27% | 3.05% | 3.48% | 5.26% | 7.80% | 0.409 | 2.19% | 50.0% | 90.6% |
| ISNE | 17,498 | 6.08% | 5.70% | 6.48% | 3.04% | 11.05% | 0.522 | 4.06% | 48.7% | 88.2% |
| JEA | 17,500 | 4.65% | 4.32% | 4.98% | 4.45% | 12.86% | 0.369 | 3.15% | 50.5% | 89.4% |
| LDWP | 17,503 | 31.66% | 8.64% | 55.19% | 36.45% | 42.16% | 0.550 | 25.67% | 43.7% | 84.9% |
| LGEE | 17,469 | 4.68% | 4.38% | 5.05% | 8.14% | 13.42% | 0.347 | 3.18% | 49.4% | 88.8% |
| MISO | 17,473 | 2.77% | 2.58% | 2.99% | 2.64% | 7.30% | 0.376 | 1.89% | 53.7% | 92.5% |
| NEVP | 17,473 | 3.14% | 2.92% | 3.33% | 8.94% | 8.63% | 0.350 | 2.11% | 49.6% | 91.1% |
| NWMT | 17,488 | 3.37% | 3.10% | 3.67% | 2.55% | 7.04% | 0.473 | 2.27% | 49.4% | 89.7% |
| NYIS | 17,488 | 4.22% | 3.96% | 4.51% | 2.63% | 9.32% | 0.438 | 2.84% | 48.4% | 89.1% |
| PACE | 17,500 | 3.36% | 3.16% | 3.56% | 5.23% | 6.53% | 0.503 | 2.27% | 47.2% | 88.5% |
| PACW | 17,503 | 3.00% | 2.85% | 3.16% | 2.68% | 6.77% | 0.438 | 2.02% | 53.3% | 94.0% |
| PGE | 17,503 | 2.86% | 2.73% | 3.03% | 1.58% | 6.29% | 0.446 | 1.93% | 52.0% | 93.0% |
| PJM | 17,406 | 3.59% | 3.34% | 3.89% | 3.50% | 8.72% | 0.405 | 2.43% | 48.8% | 88.6% |
| PNM | 17,503 | 3.12% | 3.00% | 3.26% | 5.64% | 6.10% | 0.497 | 2.08% | 50.0% | 91.3% |
| PSCO | 17,498 | 5.60% | 5.13% | 6.23% | 17.89% | 9.56% | 0.563 | 3.82% | 44.4% | 84.2% |
| PSEI | 17,503 | 3.00% | 2.84% | 3.21% | 45.88% | 7.62% | 0.386 | 2.03% | 50.4% | 92.0% |
| SC | 17,302 | 4.83% | 4.44% | 5.28% | 4.01% | 12.09% | 0.392 | 3.30% | 49.4% | 88.4% |
| SCEG | 16,880 | 5.45% | 4.57% | 6.72% | 5.66% | 13.57% | 0.364 | 3.80% | 48.4% | 88.9% |
| SCL | 17,503 | 3.47% | 3.32% | 3.63% | 3.40% | 7.13% | 0.479 | 2.31% | 51.1% | 91.1% |
| SEC | 17,160 | 12.98% | 11.81% | 14.42% | 15.35% | 23.02% | 0.561 | 9.11% | 43.7% | 80.7% |
| SOCO | 17,499 | 3.45% | 3.15% | 3.71% | 1.38% | 10.96% | 0.315 | 2.37% | 50.3% | 89.4% |
| SPA | 17,410 | 29.87% | 27.92% | 31.76% | 390.72% | 39.58% | 0.715 | 20.17% | 45.0% | 84.3% |
| SRP | 17,503 | 7.78% | 6.61% | 8.98% | 9.71% | 13.93% | 0.526 | 5.53% | 37.5% | 74.9% |
| SWPP | 17,453 | 3.35% | 3.10% | 3.63% | 10.99% | 8.28% | 0.403 | 2.26% | 48.9% | 91.1% |
| TAL | 17,500 | 5.01% | 4.70% | 5.27% | 4.26% | 13.81% | 0.366 | 3.36% | 48.2% | 88.9% |
| TEC | 17,496 | 4.44% | 4.09% | 4.75% | 4.00% | 11.63% | 0.387 | 2.99% | 51.3% | 89.9% |
| TEPC | 17,455 | 4.03% | 3.79% | 4.29% | 2.87% | 9.21% | 0.417 | 2.71% | 51.2% | 90.6% |
| TIDC | 17,421 | 3.90% | 3.64% | 4.16% | 3.18% | 8.49% | 0.432 | 2.65% | 52.4% | 90.6% |
| TPWR | 17,503 | 3.43% | 3.24% | 3.65% | 2.29% | 8.61% | 0.391 | 2.30% | 50.2% | 90.5% |
| TVA | 17,491 | 3.94% | 3.67% | 4.26% | 2.34% | 12.28% | 0.322 | 2.68% | 48.4% | 89.2% |
| WALC | 17,471 | 10.24% | 9.28% | 11.58% | 23.57% | 17.34% | 0.589 | 7.10% | 36.0% | 76.6% |

Source: real:eia930, model gbm, 51 authorities in the backtest, test year, as of 2026-09-29.

### The quantile table and the reliability diagram, gbm

Shares of actuals at or below each served level, against the level itself; degenerate levels
none, interior test yes.

| Level | Share of actuals at or below | Rows |
|---:|---:|---:|
| 5% | 5.5% | 889,573 |
| 25% | 24.1% | 889,573 |
| 50% | 48.4% | 889,573 |
| 75% | 73.1% | 889,573 |
| 95% | 94.6% | 889,573 |

Source: real:eia930, model gbm, 51 authorities in the backtest, test year, as of 2026-09-29.

| Level | Share of actuals below | Interior |
|---:|---:|---|
| 5% | 5.5% | yes |
| 25% | 24.1% | yes |
| 50% | 48.4% | yes |
| 75% | 73.1% | yes |
| 95% | 94.6% | yes |

Source: real:eia930, model gbm, 51 authorities in the backtest, test year, as of 2026-09-29.

### Peaks and ramps by authority, gbm

| Authority | Days | Peak error | Operator peak error | Naive peak error | Peak timing error | Operator timing error | Median timing error | Morning ramp error | Operator morning ramp | Evening ramp error | Operator evening ramp |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AECI | 363 | 5.03% | 1.48% | 19.18% | 1.8 h | 0.8 h | 1.0 h | 3.46% | 2.25% | 4.82% | 2.25% |
| AVA | 362 | 2.58% | 2.00% | 8.41% | 1.9 h | 1.4 h | 1.0 h | 1.98% | 1.46% | 2.40% | 1.93% |
| AZPS | 363 | 4.00% | 5.99% | 9.43% | 1.7 h | 2.0 h | 1.0 h | 4.67% | 8.72% | 4.73% | 8.59% |
| BANC | 345 | 6.05% | 16.77% | 14.68% | 1.5 h | 1.5 h | 1.0 h | 3.01% | 2.40% | 4.25% | 3.11% |
| BPAT | 363 | 2.41% | 1.73% | 6.98% | 2.0 h | 1.4 h | 1.0 h | 1.85% | 1.21% | 1.98% | 1.27% |
| CHPD | 363 | 4.15% | 3.22% | 11.82% | 1.1 h | 1.0 h | 1.0 h | 3.08% | 3.07% | 3.17% | 2.92% |
| CISO | 357 | 3.97% | 2.91% | 7.87% | 2.6 h | 3.1 h | 1.0 h | 3.79% | 17.31% | 4.30% | 10.96% |
| CPLE | 363 | 4.16% | 3.97% | 16.43% | 1.7 h | 1.7 h | 1.0 h | 3.15% | 1.97% | 3.93% | 2.67% |
| CPLW | 363 | 4.47% | 4.67% | 16.58% | 1.5 h | 1.9 h | 1.0 h | 3.00% | 1.87% | 4.17% | 2.90% |
| DOPD | 363 | 3.24% | 4.69% | 9.15% | 1.4 h | 1.3 h | 1.0 h | 2.22% | 3.00% | 2.56% | 2.99% |
| DUK | 363 | 3.66% | 3.82% | 14.82% | 1.5 h | 1.1 h | 1.0 h | 2.46% | 1.52% | 3.32% | 2.25% |
| EPE | 360 | 4.53% | 3.62% | 11.49% | 1.0 h | 1.0 h | 1.0 h | 2.86% | 2.57% | 4.63% | 3.14% |
| ERCO | 361 | 3.50% | 2.01% | 8.49% | 1.2 h | 0.7 h | 1.0 h | 1.59% | 1.90% | 2.80% | 1.60% |
| FMPP | 359 | 4.72% | 19.17% | 11.94% | 1.6 h | 2.4 h | 1.0 h | 2.37% | 3.86% | 4.58% | 3.82% |
| FPC | 363 | 5.51% | 25.17% | 13.94% | 1.4 h | 1.2 h | 1.0 h | 2.44% | 4.49% | 4.89% | 3.52% |
| FPL | 363 | 4.18% | 2.92% | 10.43% | 1.5 h | 1.1 h | 1.0 h | 2.59% | 2.40% | 4.33% | 2.59% |
| GCPD | 363 | 1.97% | 2.18% | 5.77% | 1.7 h | 1.3 h | 1.0 h | 1.51% | 1.34% | 1.89% | 1.21% |
| GVL | 343 | 4.93% | 11.22% | 14.97% | 1.4 h | 1.5 h | 1.0 h | 2.47% | 2.66% | 5.52% | 5.29% |
| HST | 362 | 4.81% | 6.06% | 11.91% | 1.4 h | 1.5 h | 1.0 h | 3.30% | 4.71% | 5.90% | 6.47% |
| IID | 359 | 5.47% | 3.61% | 15.63% | 0.7 h | 0.5 h | 1.0 h | 3.15% | 2.13% | 4.77% | 3.08% |
| IPCO | 363 | 3.31% | 4.70% | 9.07% | 1.9 h | 2.9 h | 1.0 h | 2.38% | 4.24% | 2.99% | 4.03% |
| ISNE | 362 | 3.11% | 1.22% | 8.40% | 0.9 h | 0.3 h | 1.0 h | 5.79% | 2.32% | 6.29% | 2.24% |
| JEA | 363 | 4.29% | 3.70% | 14.71% | 1.3 h | 1.0 h | 1.0 h | 2.62% | 2.22% | 4.60% | 3.23% |
| LDWP | 363 | 23.00% | 28.24% | 34.36% | 1.8 h | 1.8 h | 1.0 h | 6.17% | 7.41% | 6.35% | 5.81% |
| LGEE | 364 | 4.06% | 8.41% | 14.34% | 2.0 h | 1.4 h | 1.0 h | 3.01% | 1.97% | 4.14% | 2.16% |
| MISO | 362 | 2.62% | 2.62% | 7.97% | 1.8 h | 0.9 h | 1.0 h | 1.77% | 0.92% | 2.25% | 1.01% |
| NEVP | 354 | 3.11% | 5.59% | 10.21% | 1.4 h | 1.4 h | 1.0 h | 2.92% | 9.20% | 2.94% | 4.28% |
| NWMT | 357 | 3.27% | 2.48% | 7.42% | 2.8 h | 2.1 h | 1.0 h | 2.60% | 2.32% | 3.07% | 2.32% |
| NYIS | 362 | 2.81% | 2.55% | 8.30% | 0.8 h | 0.3 h | 1.0 h | 3.96% | 1.68% | 4.44% | 1.93% |
| PACE | 362 | 3.04% | 3.79% | 6.77% | 2.7 h | 3.1 h | 1.0 h | 2.84% | 3.64% | 3.83% | 6.13% |
| PACW | 363 | 3.31% | 2.68% | 8.66% | 1.8 h | 1.3 h | 1.0 h | 1.92% | 1.40% | 2.53% | 1.75% |
| PGE | 363 | 2.47% | 1.78% | 7.76% | 1.9 h | 1.2 h | 1.0 h | 2.13% | 1.54% | 3.20% | 1.79% |
| PJM | 363 | 3.15% | 1.96% | 9.39% | 1.9 h | 1.7 h | 1.0 h | 2.02% | 5.03% | 2.50% | 3.22% |
| PNM | 365 | 2.66% | 4.88% | 6.42% | 1.9 h | 1.4 h | 1.0 h | 2.74% | 2.85% | 3.10% | 2.64% |
| PSCO | 361 | 5.14% | 18.22% | 9.94% | 2.8 h | 3.0 h | 1.0 h | 4.66% | 9.91% | 5.16% | 8.78% |
| PSEI | 363 | 2.76% | 43.55% | 8.23% | 1.8 h | 5.1 h | 1.0 h | 1.78% | 16.15% | 2.62% | 5.51% |
| SC | 359 | 4.68% | 2.77% | 13.35% | 1.9 h | 1.6 h | 1.0 h | 3.27% | 3.09% | 3.71% | 3.21% |
| SCEG | 350 | 3.83% | 3.97% | 14.15% | 2.1 h | 2.2 h | 1.0 h | 4.15% | 4.36% | 4.43% | 4.90% |
| SCL | 363 | 3.07% | 3.63% | 7.54% | 2.2 h | 1.6 h | 1.0 h | 2.54% | 1.99% | 2.64% | 1.93% |
| SEC | 320 | 12.59% | 15.25% | 24.58% | 2.3 h | 1.5 h | 1.0 h | 6.15% | 5.21% | 10.72% | 7.07% |
| SOCO | 362 | 3.19% | 1.40% | 13.50% | 1.3 h | 0.1 h | 1.0 h | 2.35% | 0.40% | 3.18% | 0.32% |
| SPA | 349 | 24.31% | 41,690.23% | 17.32% | 6.5 h | 52.2 h | 5.0 h | 20.12% | 189.15% | 19.33% | 179.14% |
| SRP | 365 | 5.41% | 7.02% | 13.34% | 1.2 h | 1.1 h | 1.0 h | 4.14% | 3.78% | 5.12% | 3.96% |
| SWPP | 362 | 3.65% | 11.84% | 9.94% | 2.7 h | 3.4 h | 1.0 h | 1.95% | 1.82% | 2.72% | 2.16% |
| TAL | 363 | 4.65% | 5.22% | 16.13% | 1.5 h | 1.4 h | 1.0 h | 2.81% | 3.74% | 4.77% | 4.24% |
| TEC | 362 | 4.00% | 3.69% | 12.25% | 1.3 h | 1.0 h | 1.0 h | 2.46% | 2.69% | 4.52% | 3.82% |
| TEPC | 364 | 3.48% | 2.67% | 10.03% | 1.0 h | 0.8 h | 1.0 h | 3.13% | 1.98% | 4.44% | 3.52% |
| TIDC | 351 | 3.70% | 3.20% | 10.27% | 1.1 h | 0.8 h | 1.0 h | 2.80% | 2.21% | 3.79% | 2.96% |
| TPWR | 363 | 3.01% | 2.03% | 9.06% | 2.3 h | 1.4 h | 1.0 h | 2.32% | 1.28% | 2.89% | 1.82% |
| TVA | 359 | 3.47% | 2.51% | 13.72% | 2.0 h | 0.8 h | 1.0 h | 2.60% | 1.53% | 3.59% | 1.72% |
| WALC | 351 | 9.51% | 89.31% | 13.24% | 2.7 h | 4.1 h | 1.0 h | 7.15% | 10.26% | 9.86% | 13.67% |

Source: real:eia930, model gbm, 51 authorities in the backtest, test year, as of 2026-09-29.

### The own backend's choices on validation

Thresholds and penalties chosen on the validation year for every authority
(chosen on validation: yes;
36 candidate pairs, 29,325 fits).

| Authority | Heating threshold (C) | Cooling threshold (C) | Ridge penalty | Validation MAPE |
|---|---:|---:|---:|---:|
| AECI | 12.0 | 22.0 | 0.10 | 5.39% |
| AVA | 14.0 | 22.0 | 0.10 | 3.22% |
| AZPS | 12.0 | 24.0 | 0.10 | 4.96% |
| BANC | 14.0 | 24.0 | 10,000.00 | 4.33% |
| BPAT | 14.0 | 22.0 | 1,000.00 | 2.63% |
| CHPD | 12.0 | 22.0 | 1,000.00 | 3.94% |
| CISO | 10.0 | 26.0 | 10,000.00 | 4.04% |
| CPLE | 10.0 | 20.0 | 0.10 | 5.36% |
| CPLW | 10.0 | 20.0 | 100.00 | 5.36% |
| DOPD | 12.0 | 20.0 | 10,000.00 | 3.24% |
| DUK | 12.0 | 20.0 | 0.10 | 4.28% |
| EPE | 14.0 | 22.0 | 10.00 | 4.57% |
| ERCO | 12.0 | 20.0 | 10,000.00 | 3.69% |
| FMPP | 12.0 | 20.0 | 1,000.00 | 4.25% |
| FPC | 16.0 | 20.0 | 1,000.00 | 5.17% |
| FPL | 18.0 | 22.0 | 1,000.00 | 4.56% |
| GCPD | 10.0 | 20.0 | 1,000.00 | 2.04% |
| GVL | 12.0 | 20.0 | 1,000.00 | 5.18% |
| HST | 18.0 | 18.0 | 1,000.00 | 5.35% |
| IID | 18.0 | 18.0 | 1,000.00 | 28.57% |
| IPCO | 10.0 | 22.0 | 1,000.00 | 3.37% |
| ISNE | 10.0 | 20.0 | 1,000.00 | 5.89% |
| JEA | 14.0 | 20.0 | 1,000.00 | 5.03% |
| LDWP | 18.0 | 24.0 | 0.10 | 12.43% |
| LGEE | 10.0 | 20.0 | 0.10 | 4.51% |
| MISO | 8.0 | 20.0 | 100.00 | 2.94% |
| NEVP | 12.0 | 24.0 | 1,000.00 | 3.48% |
| NWMT | 16.0 | 20.0 | 0.10 | 3.57% |
| NYIS | 8.0 | 22.0 | 10,000.00 | 4.13% |
| PACE | 12.0 | 22.0 | 0.10 | 2.93% |
| PACW | 12.0 | 22.0 | 1,000.00 | 4.81% |
| PGE | 12.0 | 22.0 | 10,000.00 | 3.52% |
| PJM | 8.0 | 20.0 | 1,000.00 | 3.56% |
| PNM | 12.0 | 22.0 | 1,000.00 | 3.24% |
| PSCO | 12.0 | 22.0 | 10,000.00 | 5.53% |
| PSEI | 14.0 | 20.0 | 1,000.00 | 3.70% |
| SC | 16.0 | 22.0 | 1,000.00 | 5.42% |
| SCEG | 12.0 | 20.0 | 0.10 | 17.01% |
| SCL | 14.0 | 20.0 | 100.00 | 3.64% |
| SEC | 16.0 | 22.0 | 0.10 | 10.56% |
| SOCO | 10.0 | 20.0 | 0.10 | 3.74% |
| SPA | 8.0 | 26.0 | 10,000.00 | 31.84% |
| SRP | 12.0 | 24.0 | 0.10 | 4.37% |
| SWPP | 8.0 | 20.0 | 100.00 | 3.71% |
| TAL | 12.0 | 20.0 | 1,000.00 | 5.28% |
| TEC | 14.0 | 20.0 | 1,000.00 | 5.60% |
| TEPC | 16.0 | 26.0 | 10,000.00 | 4.38% |
| TIDC | 10.0 | 22.0 | 1,000.00 | 4.30% |
| TPWR | 12.0 | 22.0 | 1,000.00 | 3.57% |
| TVA | 10.0 | 20.0 | 0.10 | 3.97% |
| WALC | 12.0 | 24.0 | 0.10 | 7.43% |

Source: real:eia930, model own, 51 authorities in the backtest, test year, as of 2026-09-29.

### The gbm backend's refits and importance

13 monthly refits (2025-09-01, 2025-10-01, 2025-11-01, 2025-12-01, 2026-01-01, 2026-02-01, 2026-03-01, 2026-04-01, 2026-05-01, 2026-06-01, 2026-07-01, 2026-08-01, 2026-09-01), every
3 origin days in training,
2,677,186 rows in the calibration fit and
891,769 calibration rows.

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

## The hierarchy: accuracy by level before and after each method

159 nodes (51 authorities,
83 eligible subregions under
8 authorities, 8
remainder nodes), 363 origins, shrinkage intensity
0.002. Coherence gaps: bottom up
0.0000 MW, top down 0.0000 MW,
MinT 0.0000 MW; the base forecasts disagree by up to
71,796 MW. Helped at bottom_up at the lower 48 level; bottom_up at the interconnection level; bottom_up at the region level; mint at the lower 48 level; mint at the interconnection level; mint at the region level; hurt at
top_down at the interconnection level; top_down at the region level; top_down at the authority level; top_down at the subregion level; mint at the authority level; mint at the subregion level; best method summed over levels: bottom_up.

| Method | Level | Nodes | Rows | MAPE | lower | upper | 90 pct coverage |
|---|---|---:|---:|---:|---:|---:|---:|
| base | lower 48 | 1 | 15,049 | 2.65% | 2.49% | 2.81% | 90.0% |
| base | interconnection | 3 | 49,755 | 3.04% | 2.90% | 3.16% | 89.9% |
| base | region | 13 | 223,815 | 3.93% | 3.77% | 4.04% | 88.2% |
| base | authority | 51 | 885,665 | 5.65% | 5.23% | 6.03% | 88.3% |
| base | subregion | 83 | 1,436,191 | 8.53% | 8.29% | 8.71% | 88.4% |
| bottom_up | lower 48 | 1 | 15,049 | 2.15% | 1.98% | 2.28% | 100.0% |
| bottom_up | interconnection | 3 | 49,755 | 2.82% | 2.70% | 2.93% | 98.9% |
| bottom_up | region | 13 | 223,815 | 3.85% | 3.70% | 3.95% | 94.4% |
| bottom_up | authority | 51 | 885,665 | 5.65% | 5.23% | 6.01% | 89.4% |
| bottom_up | subregion | 83 | 1,436,191 | 8.53% | 8.27% | 8.71% | 88.4% |
| top_down | lower 48 | 1 | 15,049 | 2.65% | 2.49% | 2.80% | 90.1% |
| top_down | interconnection | 3 | 49,755 | 7.04% | 6.50% | 7.70% | 51.7% |
| top_down | region | 13 | 223,815 | 9.35% | 8.91% | 9.80% | 39.7% |
| top_down | authority | 51 | 885,665 | 15.10% | 14.28% | 16.14% | 28.0% |
| top_down | subregion | 83 | 1,436,191 | 14.28% | 13.64% | 14.89% | 30.4% |
| mint | lower 48 | 1 | 15,049 | 2.14% | 1.99% | 2.24% | 100.0% |
| mint | interconnection | 3 | 49,755 | 2.82% | 2.71% | 2.92% | 98.7% |
| mint | region | 13 | 223,815 | 3.85% | 3.71% | 3.93% | 94.8% |
| mint | authority | 51 | 885,665 | 5.67% | 5.27% | 6.04% | 88.2% |
| mint | subregion | 83 | 1,436,191 | 10.01% | 9.64% | 10.33% | 88.0% |

Source: real:eia930, model own, 159 nodes of the hierarchy, test year, as of 2026-09-29.

| Method | Level | Base MAPE | Reconciled MAPE | Change | Verdict |
|---|---|---:|---:|---:|---|
| bottom_up | lower 48 | 2.65% | 2.15% | -0.5% | helped |
| bottom_up | interconnection | 3.04% | 2.82% | -0.2% | helped |
| bottom_up | region | 3.93% | 3.85% | -0.1% | helped |
| bottom_up | authority | 5.65% | 5.65% | 0.0% | unchanged |
| bottom_up | subregion | 8.53% | 8.53% | 0.0% | unchanged |
| top_down | lower 48 | 2.65% | 2.65% | 0.0% | unchanged |
| top_down | interconnection | 3.04% | 7.04% | +4.0% | hurt |
| top_down | region | 3.93% | 9.35% | +5.4% | hurt |
| top_down | authority | 5.65% | 15.10% | +9.5% | hurt |
| top_down | subregion | 8.53% | 14.28% | +5.7% | hurt |
| mint | lower 48 | 2.65% | 2.14% | -0.5% | helped |
| mint | interconnection | 3.04% | 2.82% | -0.2% | helped |
| mint | region | 3.93% | 3.85% | -0.1% | helped |
| mint | authority | 5.65% | 5.67% | 0.0% | hurt |
| mint | subregion | 8.53% | 10.01% | +1.5% | hurt |

Source: real:eia930, model own, 159 nodes of the hierarchy, test year, as of 2026-09-29.

The subregion series in the source do not exactly match their authority's demand: mean absolute
gap 0.78%, worst 3.62%
(ISNE).

| Authority | Hours compared | Mean absolute gap | Median absolute gap | Mean signed gap |
|---|---:|---:|---:|---:|
| BHBA | 2,856 | 1.68% | 1.58% | -1.7% |
| CISO | 72,111 | 0.00% | 0.00% | 0.0% |
| ERCO | 64,203 | 0.29% | 0.09% | +0.2% |
| ISNE | 72,069 | 3.62% | 2.24% | -0.2% |
| MISO | 72,215 | 0.16% | 0.04% | -0.2% |
| NYIS | 72,271 | 0.03% | 0.03% | 0.0% |
| PJM | 70,239 | 1.59% | 0.81% | -1.5% |
| PNM | 24,048 | 0.30% | 0.15% | -0.2% |
| SWPP | 70,702 | 0.08% | 0.00% | 0.0% |
| SWPW | 4,343 | 0.01% | 0.00% | 0.0% |

Source: real:eia930, every six month file from 2018_Jul_Dec, as of 2026-09-29.

## Events

Threshold 6.0 standardized residuals held for
3 hours, chosen on the demonstration grid's validation year at
a false alarm cost of 1.0 and a missed event cost of
25.0 from the grid 2.0 to 6.0
(cost 5.0, interior no).

| Threshold | False alarms | Missed load sheds | Cost |
|---:|---:|---:|---:|
| 2.0 | 702 | 0 | 702.0 |
| 2.5 | 324 | 0 | 324.0 |
| 3.0 | 140 | 0 | 140.0 |
| 3.5 | 65 | 0 | 65.0 |
| 4.0 | 29 | 0 | 29.0 |
| 5.0 | 15 | 0 | 15.0 |
| 6.0 | 5 | 0 | 5.0 |

Source: simulated, model own, the demonstration grid, validation year for the choice and test year for the grade, seed 13, as of 2026-09-29.

On the known events table: 3 of 10 rows
detected (30%), median delay 5.7
hours, 0 false alarms in 4,924
window hours outside the events (0.00 per thousand
hours). Missed: covid_2020 at NYIS, covid_2020 at MISO, ida_2021 at MISO.8910, ida_2021 at MISO, elliott_2022 at TVA, elliott_2022 at DUK, elliott_2022 at CPLE.

| Event | Node | Onset (UTC) | Verdict | Detection hour (UTC) | Delay hours | Peak z | False alarms in window |
|---|---|---|---|---|---:|---:|---:|
| covid_2020 | NYIS | 2020-03-16 00:00 | missed | none | not applicable | not applicable | 0 |
| covid_2020 | MISO | 2020-03-18 00:00 | missed | none | not applicable | not applicable | 0 |
| uri_2021 | ERCO | 2021-02-15 07:20 | detected | 2021-02-15 13:00 | 5.7 | 8.9 | 0 |
| ida_2021 | MISO.8910 | 2021-08-29 17:00 | missed | none | not applicable | not applicable | 0 |
| ida_2021 | MISO | 2021-08-29 17:00 | missed | none | not applicable | not applicable | 0 |
| elliott_2022 | TVA | 2022-12-23 15:31 | missed | none | not applicable | not applicable | 0 |
| elliott_2022 | DUK | 2022-12-24 11:00 | missed | none | not applicable | not applicable | 0 |
| elliott_2022 | CPLE | 2022-12-24 11:00 | missed | none | not applicable | not applicable | 0 |
| beryl_2024 | ERCO.COAS | 2024-07-08 09:00 | detected | 2024-07-08 12:00 | 3.0 | 19.2 | 0 |
| beryl_2024 | ERCO | 2024-07-08 09:00 | detected | 2024-07-08 20:00 | 11.0 | 7.4 | 0 |

Source: real:eia930, model own, the known events table, each in a window of ten days either side, as of 2026-09-29.

On the demonstration grid's test year: 1 of
2 planted load sheds detected (50%),
6 of 6 planted defects recovered as
defects, 0 defects reported as demand events,
8 false alarms among 9 demand event
alerts (precision 11%). By condition and seed, the recovery study table
below carries the detector's recall and precision.

Over the real test year: 277 alerts across 51
authorities, 71 demand events and 206
data defects, 0.62 per thousand hours.

| Authority | Alerts | Demand events | Data defects | Alert hours | Peak z |
|---|---:|---:|---:|---:|---:|
| SEC | 37 | 1 | 36 | 169 | 17.6 |
| SRP | 29 | 29 | 0 | 148 | 18.9 |
| SPA | 26 | 0 | 26 | 45 | not applicable |
| WALC | 26 | 10 | 16 | 69 | 10.5 |
| BANC | 17 | 0 | 17 | 17 | not applicable |
| GVL | 16 | 0 | 16 | 254 | not applicable |
| TIDC | 14 | 1 | 13 | 44 | 6.5 |
| NEVP | 11 | 1 | 10 | 18 | 7.2 |
| CISO | 7 | 0 | 7 | 54 | not applicable |
| EPE | 7 | 1 | 6 | 55 | 7.7 |
| FPL | 7 | 4 | 3 | 30 | 9.7 |
| SC | 7 | 0 | 7 | 99 | not applicable |
| FMPP | 6 | 1 | 5 | 21 | 7.5 |
| NWMT | 6 | 0 | 6 | 7 | not applicable |
| HST | 5 | 4 | 1 | 69 | 17.1 |
| IID | 5 | 0 | 5 | 98 | not applicable |
| SWPP | 5 | 4 | 1 | 45 | 9.4 |
| TVA | 5 | 0 | 5 | 5 | not applicable |
| LDWP | 4 | 4 | 0 | 209 | 80.0 |
| CHPD | 3 | 3 | 0 | 13 | 7.1 |
| MISO | 3 | 0 | 3 | 14 | not applicable |
| SCEG | 3 | 0 | 3 | 288 | not applicable |
| TEC | 3 | 1 | 2 | 10 | 6.7 |
| AZPS | 2 | 0 | 2 | 15 | not applicable |
| BPAT | 2 | 2 | 0 | 6 | 10.1 |
| CPLE | 2 | 1 | 1 | 28 | 7.1 |
| FPC | 2 | 1 | 1 | 33 | 7.3 |
| GCPD | 2 | 1 | 1 | 15 | 15.6 |
| ISNE | 2 | 1 | 1 | 8 | 7.4 |
| PJM | 2 | 0 | 2 | 47 | not applicable |
| PSCO | 2 | 1 | 1 | 8 | 14.1 |
| AVA | 1 | 0 | 1 | 2 | not applicable |
| CPLW | 1 | 0 | 1 | 25 | not applicable |
| DUK | 1 | 0 | 1 | 25 | not applicable |
| ERCO | 1 | 0 | 1 | 48 | not applicable |
| LGEE | 1 | 0 | 1 | 16 | not applicable |
| NYIS | 1 | 0 | 1 | 6 | not applicable |
| PACE | 1 | 0 | 1 | 1 | not applicable |
| SOCO | 1 | 0 | 1 | 1 | not applicable |
| TEPC | 1 | 0 | 1 | 24 | not applicable |

Source: real:eia930, model own, 51 authorities in the backtest, test year, as of 2026-09-29.

| Authority | Start (UTC) | Hours | Direction | Peak z | Mean z | Flags |
|---|---|---:|---|---:|---:|---|
| LDWP | 2026-09-26 11:00 | 45 | mixed | 80.0 | 10.9 | none |
| LDWP | 2026-01-01 09:00 | 120 | low | 41.5 | -5.2 | none |
| LDWP | 2026-04-18 08:00 | 41 | mixed | 30.8 | 0.5 | none |
| SRP | 2026-05-07 05:00 | 15 | high | 18.9 | 11.3 | none |
| SEC | 2025-10-23 21:00 | 16 | high | 17.6 | 12.2 | demand_nonpositive,demand_spike |
| HST | 2026-09-24 10:00 | 38 | high | 17.1 | 9.2 | none |
| GCPD | 2026-05-29 05:00 | 14 | low | 15.6 | -9.6 | none |
| PSCO | 2026-04-14 05:00 | 7 | low | 14.1 | -10.1 | none |
| SRP | 2026-09-28 21:00 | 4 | low | 13.3 | -11.4 | none |
| SRP | 2026-04-29 14:00 | 6 | high | 11.6 | 8.4 | none |
| SRP | 2026-05-06 09:00 | 5 | high | 11.0 | 8.9 | none |
| SRP | 2026-05-11 11:00 | 7 | high | 10.8 | 8.2 | none |
| WALC | 2026-09-15 05:00 | 3 | high | 10.5 | 8.2 | none |
| SRP | 2026-05-31 13:00 | 12 | high | 10.4 | 7.5 | none |
| BPAT | 2025-10-05 05:00 | 3 | low | 10.1 | -9.6 | none |
| WALC | 2026-04-07 15:00 | 11 | low | 9.9 | -8.8 | none |
| FPL | 2026-02-01 04:00 | 9 | high | 9.7 | 8.2 | none |
| SRP | 2026-09-23 20:00 | 3 | high | 9.5 | 8.0 | none |
| SWPP | 2025-10-12 06:00 | 8 | high | 9.4 | 8.2 | none |
| SRP | 2026-05-19 09:00 | 3 | high | 9.3 | 8.0 | none |
| SRP | 2026-06-07 11:00 | 3 | low | 9.1 | -8.1 | none |
| SRP | 2026-05-12 08:00 | 8 | low | 9.0 | -8.0 | none |
| SRP | 2026-05-15 09:00 | 6 | low | 8.9 | -8.0 | none |
| SRP | 2026-09-18 09:00 | 5 | low | 8.8 | -7.7 | none |
| WALC | 2026-04-10 15:00 | 4 | high | 8.8 | 7.6 | none |

Source: real:eia930, model own, 51 authorities in the backtest, test year, as of 2026-09-29.

## The recovery study on the simulator

6 conditions with 20 seeds each,
120 runs in 3,565.2 seconds; the known skill of the oracle
forecaster against the synthetic operator is 50.7%. The harness is
furthest from the known skill under missing 5 pct; coverage is
furthest from nominal under temperature sensitivity 0.5.

| Condition | Harness skill bias | Interval covers the known skill | Operator MAPE measured | own MAPE | own 50 pct coverage | own 90 pct coverage | Thresholds within 2 C | Holiday effect error |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base (sensitivity 1.0, noise 1 pct, no missing) | -0.1% | 86% | 2.44% | 2.27% | 50.7% | 90.3% | 97% | 1.05% |
| temperature sensitivity 0.5 | -0.1% | 86% | 2.44% | 1.72% | 50.8% | 90.5% | 91% | 0.59% |
| temperature sensitivity 2.0 | -0.1% | 86% | 2.44% | 3.12% | 50.6% | 90.2% | 99% | 1.65% |
| noise 3 pct | -0.1% | 86% | 2.44% | 3.44% | 50.5% | 90.3% | 91% | 1.05% |
| missing 1 pct | -0.1% | 87% | 2.44% | 2.35% | 50.8% | 90.3% | 92% | 1.06% |
| missing 5 pct | -0.1% | 84% | 2.44% | 2.55% | 51.0% | 90.3% | 79% | 1.06% |

Source: simulated, model own, the recovery study, 20 seeds, as of 2026-09-29.

Detector by condition (mean over seeds): base recall on load sheds
67.5%, on defects 100.0%,
precision 20.8%, defects called events
0.000; missing 5 percent: recall on load sheds
67.5%, precision
18.5%; noise 3 percent: recall on load
sheds 62.5%. Reconciliation by condition: MinT
gain at the top against the truth 0.011 (base),
0.014 (missing 5 percent); at the leaves
-0.001 (base).

## The meter

5,358 of 5,550 households profiled over
2012-12-01 to 2013-12-01; 3
clusters chosen by the silhouette on 2,679 validation
households (0.129).

| Clusters | Validation silhouette |
|---:|---:|
| 3 | 0.129 |
| 4 | 0.121 |
| 5 | 0.121 |
| 6 | 0.097 |
| 7 | 0.096 |
| 8 | 0.070 |

Source: real:lcl, 5358 households with a full profile over the year before the test period, as of 2026-09-29.

| Cluster | Shape | Households | Mean kWh per half hour | Share of evening peak | dToU share |
|---:|---|---:|---:|---:|---:|
| 0 | evening peak | 2,502 | 0.206 | 48.8% | 20.2% |
| 1 | evening peak | 2,802 | 0.213 | 50.5% | 20.8% |
| 2 | night heavy | 54 | 0.405 | 0.8% | 0.0% |

Source: real:lcl, 5358 households with a full profile over the year before the test period, as of 2026-09-29.

The time of use analysis, pre-registered in `docs/tou_plan.md` (SHA-256
`b1c595ba7016ae13bf893e84d62b3e83418606b0e52e1b76e5cac9f2bce64c5f`): 1,088 matched pairs from
1,088 dynamic tariff households and 4,243
standard ones (0 dropped), 69 high price events
averaging 5.7 hours. Response -5.8%
(-7.0% to -4.7%),
-0.160 kWh per household per event (-0.202 to
-0.124); rebound +0.2%
(-0.7% to +1.0%) in the three hours
after; 4 of 4 event types different from
zero after Benjamini-Hochberg.

| Event type | Events | Response | lower | upper | p value | After correction |
|---|---:|---:|---:|---:|---:|---|
| night | 11 | -6.0% | -7.9% | -3.3% | 0.000 | different from zero |
| morning | 15 | -9.4% | -10.6% | -8.0% | 0.000 | different from zero |
| afternoon | 3 | -6.5% | -6.5% | -6.5% | 0.000 | different from zero |
| evening | 40 | -4.8% | -6.0% | -3.4% | 0.000 | different from zero |

Source: real:lcl, 1088 matched pairs over 69 high price events of 2013, 500 seeds, as of 2026-09-29.

The cluster forecast: 4,485 households
(84% of those profiled) over 2013-12-01
to 2014-02-28, 352 origins, gbm without
weather, shrinkage intensity 0.00; MinT
helped at the total and hurt
at the clusters; coherence gaps bottom up 0.000000 kWh, MinT
0.000000 kWh.

| Level | Method | MAPE | lower | upper | 90 pct coverage |
|---|---|---:|---:|---:|---:|
| panel total | base | 4.30% | 3.76% | 5.05% | 98.6% |
| panel total | bottom_up | 4.27% | 3.73% | 4.92% | 98.9% |
| panel total | mint | 4.26% | 3.73% | 4.89% | 98.8% |
| clusters | base | 6.78% | 5.94% | 7.61% | 97.8% |
| clusters | bottom_up | 6.78% | 5.84% | 7.59% | 97.8% |
| clusters | mint | 9.12% | 7.46% | 10.73% | 92.6% |

Source: real:lcl, model gbm, 4485 households reporting through the whole forecast window, 352 origins, as of 2026-09-29.

| Cluster | Shape | Households | Evening kW per household | Share of the evening peak | Value of a 10 pct cut, GBP per household |
|---|---|---:|---:|---:|---:|
| 1 | evening peak | 2,802 | 0.58 | 50.5% | 3.5 |
| 0 | evening peak | 2,502 | 0.63 | 48.8% | 3.8 |
| 2 | night heavy | 54 | 0.47 | 0.8% | 2.8 |

Source: real:lcl, model gbm, 4485 households reporting through the whole forecast window, 352 origins, as of 2026-09-29.

## The registry and the live log

Served: gbm (gbm cleared every gate with the best headline (wins minus losses +1)); latency source
live, 40 requests.

| Backend | Gate | Result | Value | Threshold | Evidence |
|---|---|---|---:|---|---|
| own | mape_not_worse_than_naive | pass | 0.0000 | 0.0 | 51 authorities; worse than the naive in 0 |
| own | skill_not_significantly_negative | pass | 0.0000 | 0.5 | significantly worse than the operator in 0 of 44 comparable authorities |
| own | coverage_90_on_validation | pass | 0.9008 | 0.85 to 0.95 | empirical 90 percent coverage on the validation year 0.901 |
| own | peak_timing_median | pass | 1.0000 | 2.0 | median absolute peak timing error 1.0 hours over the test year |
| own | coherence_exact | pass | 0.0000 | 0.001 | largest gap after reconciliation bottom_up 0.000000 MW, mint 0.000000 MW, top_down 0.000000 MW |
| own | p99_latency | pass | 287.2000 | 2000.0 | p99 of POST /v1/forecasts 287 ms (live, 40 requests) |
| own | leakage_check_green | pass | 0.0000 | 1e-09 | AECI: 60 design rows recomputed at their origin, largest gap 0.00e+00; the leaky lag was refused |
| gbm | mape_not_worse_than_naive | pass | 0.0000 | 0.0 | 51 authorities; worse than the naive in 0 |
| gbm | skill_not_significantly_negative | pass | 0.0000 | 0.5 | significantly worse than the operator in 0 of 44 comparable authorities |
| gbm | coverage_90_on_validation | pass | 0.9003 | 0.85 to 0.95 | empirical 90 percent coverage on the validation year 0.900 |
| gbm | peak_timing_median | pass | 1.0000 | 2.0 | median absolute peak timing error 1.0 hours over the test year |
| gbm | coherence_exact | pass | 0.0000 | 0.001 | largest gap after reconciliation bottom_up 0.000000 MW, mint 0.000000 MW, top_down 0.000000 MW |
| gbm | p99_latency | pass | 287.2000 | 2000.0 | p99 of POST /v1/forecasts 287 ms (live, 40 requests) |
| gbm | leakage_check_green | pass | 0.0000 | 1e-09 | AECI: 60 design rows recomputed at their origin, largest gap 0.00e+00; the leaky lag was refused |

Source: real:eia930, model both, the candidate backends over the test year, as of 2026-09-29.

Deploy: deployed at https://lookahead-grid-api.fly.dev, checked from AJAY, Windows, PowerShell 5.1.26100.9444
at 2026-09-29T23:59:24.0034369Z; 48 rows read back, first hour
median 2,908 MW, 48 rows scored, unscored share
0.0%, 2 audit entries, audit before response
yes, statement present yes.
Live check: not checked at not yet in no browser yet,
0 of 0 routes, forecast none,
first probe , recorded session shown with the API asleep:
no. Latency: 2 measurement
files; local p50 25 ms and p99 42 ms
for issuing a forecast, p50 6 ms and p99
11 ms for reading one back, over 60
requests; live measured.

## Data

| Authority | Hours | Demand missing | Zero or negative | Spike | Duplicated hour | Missing hour | Operator forecast missing | Quarantined | Share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AEC | 27,792 | 214 | 0 | 0 | 0 | 0 | 279 | 214 | 0.77% |
| AECI | 72,312 | 40 | 0 | 0 | 0 | 0 | 0 | 40 | 0.06% |
| AVA | 72,312 | 24 | 3 | 18 | 0 | 0 | 24 | 45 | 0.06% |
| AZPS | 72,312 | 62 | 19 | 6 | 0 | 0 | 48 | 87 | 0.12% |
| BANC | 72,312 | 345 | 235 | 98 | 0 | 0 | 703 | 678 | 0.94% |
| BHBA | 4,368 | 1,512 | 0 | 0 | 0 | 0 | 1,488 | 1,512 | 34.62% |
| BPAT | 72,312 | 24 | 0 | 0 | 0 | 0 | 0 | 24 | 0.03% |
| CHPD | 72,312 | 114 | 1 | 0 | 0 | 0 | 89 | 115 | 0.16% |
| CISO | 72,312 | 176 | 0 | 0 | 0 | 0 | 120 | 176 | 0.24% |
| CPLE | 72,312 | 167 | 1 | 0 | 0 | 0 | 146 | 168 | 0.23% |
| CPLW | 72,312 | 144 | 0 | 0 | 0 | 0 | 124 | 144 | 0.20% |
| DOPD | 72,312 | 1,608 | 0 | 0 | 0 | 0 | 624 | 1,608 | 2.22% |
| DUK | 72,312 | 72 | 0 | 0 | 0 | 0 | 52 | 72 | 0.10% |
| EPE | 72,312 | 83 | 0 | 0 | 0 | 0 | 48 | 83 | 0.11% |
| ERCO | 72,312 | 144 | 0 | 0 | 0 | 0 | 144 | 144 | 0.20% |
| FMPP | 72,312 | 197 | 9 | 23 | 0 | 0 | 246 | 229 | 0.32% |
| FPC | 72,312 | 72 | 2 | 0 | 0 | 0 | 53 | 74 | 0.10% |
| FPL | 72,312 | 783 | 51 | 6 | 0 | 0 | 204 | 840 | 1.16% |
| GCPD | 72,312 | 26 | 0 | 0 | 0 | 0 | 40 | 26 | 0.04% |
| GVL | 72,312 | 1,534 | 1 | 1 | 0 | 0 | 1,277 | 1,536 | 2.12% |
| HST | 72,312 | 89 | 0 | 1 | 0 | 0 | 289 | 90 | 0.12% |
| IID | 72,312 | 192 | 492 | 0 | 0 | 0 | 264 | 684 | 0.95% |
| IPCO | 72,312 | 24 | 0 | 0 | 0 | 0 | 0 | 24 | 0.03% |
| ISNE | 72,312 | 27 | 0 | 0 | 0 | 0 | 0 | 27 | 0.04% |
| JEA | 72,312 | 338 | 0 | 0 | 0 | 0 | 3,189 | 338 | 0.47% |
| LDWP | 72,312 | 448 | 4 | 0 | 0 | 0 | 652 | 452 | 0.63% |
| LGEE | 72,312 | 214 | 19 | 1 | 0 | 0 | 78 | 234 | 0.32% |
| MISO | 72,312 | 97 | 0 | 0 | 0 | 0 | 96 | 97 | 0.13% |
| NEVP | 72,312 | 42 | 27 | 9 | 0 | 0 | 58 | 78 | 0.11% |
| NSB | 13,345 | 2,138 | 3 | 5 | 0 | 0 | 2,162 | 2,146 | 16.08% |
| NWMT | 72,312 | 98 | 77 | 12 | 0 | 0 | 511 | 187 | 0.26% |
| NYIS | 72,312 | 24 | 12 | 0 | 0 | 0 | 0 | 36 | 0.05% |
| OVEC | 3,673 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0.00% |
| PACE | 72,312 | 24 | 3 | 6 | 0 | 0 | 72 | 33 | 0.05% |
| PACW | 72,312 | 24 | 1 | 2 | 0 | 0 | 0 | 27 | 0.04% |
| PGE | 72,312 | 73 | 0 | 1 | 0 | 0 | 24 | 74 | 0.10% |
| PJM | 72,312 | 214 | 0 | 4 | 0 | 0 | 263 | 218 | 0.30% |
| PNM | 72,312 | 24 | 48 | 0 | 0 | 0 | 0 | 72 | 0.10% |
| PSCO | 72,312 | 48 | 14 | 2 | 0 | 0 | 958 | 64 | 0.09% |
| PSEI | 72,312 | 13,103 | 0 | 0 | 0 | 0 | 0 | 13,103 | 18.12% |
| SC | 72,312 | 278 | 0 | 0 | 0 | 0 | 273 | 278 | 0.38% |
| SCEG | 72,312 | 505 | 0 | 0 | 0 | 0 | 894 | 505 | 0.70% |
| SCL | 72,312 | 33 | 2 | 5 | 0 | 0 | 294 | 40 | 0.06% |
| SEC | 72,312 | 509 | 7,597 | 1,898 | 0 | 0 | 299 | 10,004 | 13.83% |
| SOCO | 72,312 | 170 | 1 | 3 | 0 | 0 | 2,383 | 174 | 0.24% |
| SPA | 72,312 | 192 | 86 | 13 | 0 | 0 | 1,116 | 291 | 0.40% |
| SRP | 72,312 | 845 | 0 | 20 | 0 | 0 | 5,740 | 865 | 1.20% |
| SWPP | 72,312 | 1,513 | 0 | 1 | 0 | 0 | 672 | 1,514 | 2.09% |
| SWPW | 4,368 | 25 | 0 | 0 | 0 | 0 | 456 | 25 | 0.57% |
| TAL | 72,312 | 744 | 0 | 0 | 0 | 0 | 0 | 744 | 1.03% |
| TEC | 72,312 | 105 | 2 | 0 | 0 | 0 | 74 | 107 | 0.15% |
| TEPC | 72,312 | 1,274 | 1 | 1 | 0 | 0 | 482 | 1,276 | 1.76% |
| TIDC | 72,312 | 144 | 231 | 0 | 0 | 0 | 120 | 375 | 0.52% |
| TPWR | 72,312 | 24 | 0 | 0 | 0 | 0 | 0 | 24 | 0.03% |
| TVA | 72,312 | 49 | 364 | 341 | 0 | 0 | 87 | 754 | 1.04% |
| WACM | 67,944 | 144 | 64 | 7 | 0 | 0 | 312 | 215 | 0.32% |
| WALC | 72,312 | 72 | 44 | 46 | 0 | 0 | 24 | 162 | 0.22% |
| WAUW | 67,944 | 2 | 2 | 0 | 0 | 0 | 0 | 4 | 0.01% |

Source: real:eia930, every six month file from 2018_Jul_Dec, as of 2026-09-29.

| Authority | Region | Reports demand | Hours in files | Share of its span with demand | Validation coverage | Test coverage | In the backtest | Operator forecast to demand, validation median | Operator forecast to demand, test median | Operator comparable |
|---|---|---|---:|---:|---:|---:|---|---:|---:|---|
| AEC | SE | yes | 27,792 | 99.3% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| AECI | MIDW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 1.00 | 1.00 | yes |
| AVA | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 1.00 | 1.00 | yes |
| AVRN | NW | no | 71,568 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| AZPS | SW | yes | 72,312 | 99.9% | 100.0% | 99.8% | yes | 0.96 | 0.94 | yes |
| BANC | CAL | yes | 72,312 | 99.9% | 100.0% | 99.8% | yes | 1.00 | 1.01 | yes |
| BHBA | NW | yes | 4,368 | 65.7% | 0.0% | 32.5% | no | not applicable | 0.97 | no |
| BPAT | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 1.00 | 1.00 | yes |
| CHPD | NW | yes | 72,312 | 99.9% | 100.0% | 100.0% | yes | 1.00 | 1.00 | yes |
| CISO | CAL | yes | 72,312 | 99.8% | 99.2% | 99.4% | yes | 0.95 | 0.96 | yes |
| CPLE | CAR | yes | 72,312 | 99.8% | 100.0% | 99.7% | yes | 1.01 | 1.00 | yes |
| CPLW | CAR | yes | 72,312 | 99.8% | 100.0% | 99.7% | yes | 0.99 | 1.00 | yes |
| DEAA | SW | no | 72,288 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| DOPD | NW | yes | 72,312 | 97.8% | 100.0% | 100.0% | yes | 1.00 | 1.03 | yes |
| DUK | CAR | yes | 72,312 | 99.9% | 100.0% | 99.7% | yes | 1.00 | 1.01 | yes |
| EEI | MIDW | no | 14,593 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| EPE | SW | yes | 72,312 | 99.9% | 100.0% | 99.4% | yes | 1.00 | 0.99 | yes |
| ERCO | TEX | yes | 72,312 | 99.9% | 100.0% | 99.5% | yes | 1.01 | 1.00 | yes |
| FMPP | FLA | yes | 72,312 | 99.8% | 99.6% | 99.9% | yes | 1.01 | 0.76 | no |
| FPC | FLA | yes | 72,312 | 99.9% | 100.0% | 99.7% | yes | 0.76 | 0.76 | no |
| FPL | FLA | yes | 72,312 | 99.0% | 99.7% | 100.0% | yes | 1.01 | 1.00 | yes |
| GCPD | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 0.99 | 0.98 | yes |
| GLHB | MIDW | no | 21,959 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| GRID | NW | no | 72,288 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| GRIF | SW | no | 46,776 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| GVL | FLA | yes | 72,312 | 97.9% | 99.0% | 97.1% | yes | 0.91 | 0.89 | no |
| GWA | NW | no | 72,288 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| HGMA | SW | no | 60,648 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| HST | FLA | yes | 72,312 | 99.9% | 100.0% | 100.0% | yes | 1.01 | 1.01 | yes |
| IID | CAL | yes | 72,312 | 99.8% | 97.3% | 98.9% | yes | 1.00 | 1.00 | yes |
| IPCO | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 1.00 | 0.99 | yes |
| ISNE | NE | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 0.99 | 0.99 | yes |
| JEA | FLA | yes | 72,312 | 99.6% | 99.7% | 100.0% | yes | 1.03 | 1.03 | yes |
| LDWP | CAL | yes | 72,312 | 99.7% | 100.0% | 100.0% | yes | 0.93 | 0.91 | yes |
| LGEE | MIDW | yes | 72,312 | 99.7% | 100.0% | 99.8% | yes | 0.92 | 0.92 | yes |
| MISO | MIDW | yes | 72,312 | 99.9% | 99.7% | 99.8% | yes | 1.02 | 1.02 | yes |
| NEVP | NW | yes | 72,312 | 100.0% | 99.8% | 99.8% | yes | 0.95 | 0.93 | yes |
| NSB | FLA | yes | 13,345 | 86.5% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| NWMT | NW | yes | 72,312 | 99.9% | 100.0% | 99.9% | yes | 1.00 | 1.00 | yes |
| NYIS | NY | yes | 72,312 | 100.0% | 100.0% | 99.9% | yes | 0.98 | 0.98 | yes |
| OVEC | MIDA | yes | 3,673 | 100.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| PACE | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 1.02 | 1.03 | yes |
| PACW | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 1.04 | 1.01 | yes |
| PGE | NW | yes | 72,312 | 99.9% | 100.0% | 100.0% | yes | 1.00 | 1.00 | yes |
| PJM | MIDA | yes | 72,312 | 99.7% | 99.7% | 99.5% | yes | 0.98 | 0.98 | yes |
| PNM | SW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 0.93 | 0.95 | yes |
| PSCO | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 0.94 | 0.83 | no |
| PSEI | NW | yes | 72,312 | 86.5% | 100.0% | 100.0% | yes | 0.72 | 0.53 | no |
| SC | CAR | yes | 72,312 | 99.6% | 99.9% | 98.9% | yes | 1.02 | 1.01 | yes |
| SCEG | CAR | yes | 72,312 | 99.3% | 99.2% | 96.7% | yes | 0.98 | 0.97 | yes |
| SCL | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 0.98 | 0.97 | yes |
| SEC | FLA | yes | 72,312 | 99.3% | 98.0% | 98.1% | yes | 0.96 | 0.94 | yes |
| SEPA | SE | no | 72,288 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| SIKE | MIDW | no | 11,640 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| SOCO | SE | yes | 72,312 | 99.8% | 100.0% | 100.0% | yes | 0.99 | 0.99 | yes |
| SPA | CENT | yes | 72,312 | 99.8% | 99.8% | 99.5% | yes | 2.04 | 1.06 | no |
| SRP | SW | yes | 72,312 | 99.7% | 100.0% | 100.0% | yes | 0.97 | 1.01 | yes |
| SWPP | CENT | yes | 72,312 | 100.0% | 100.0% | 99.7% | yes | 1.01 | 1.11 | no |
| SWPW | NW | yes | 4,368 | 100.0% | 0.0% | 49.5% | no | not applicable | 1.01 | no |
| TAL | FLA | yes | 72,312 | 99.0% | 100.0% | 100.0% | yes | 0.99 | 0.99 | yes |
| TEC | FLA | yes | 72,312 | 99.9% | 100.0% | 100.0% | yes | 1.01 | 1.01 | yes |
| TEPC | SW | yes | 72,312 | 98.6% | 100.0% | 99.7% | yes | 1.00 | 1.00 | yes |
| TIDC | CAL | yes | 72,312 | 99.8% | 100.0% | 99.5% | yes | 1.00 | 1.00 | yes |
| TPWR | NW | yes | 72,312 | 100.0% | 100.0% | 100.0% | yes | 1.01 | 1.01 | yes |
| TVA | TEN | yes | 72,312 | 100.0% | 100.0% | 99.9% | yes | 1.01 | 1.01 | yes |
| WACM | NW | yes | 67,944 | 99.8% | 99.9% | 48.8% | no | 0.84 | 0.88 | no |
| WALC | SW | yes | 72,312 | 99.9% | 99.6% | 99.8% | yes | 1.00 | 1.00 | yes |
| WAUW | NW | yes | 67,944 | 100.0% | 100.0% | 50.5% | no | 1.02 | 1.03 | yes |
| WWA | NW | no | 63,576 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |
| YAD | CAR | no | 72,288 | 0.0% | 0.0% | 0.0% | no | not applicable | not applicable | no |

Source: real:eia930, every six month file from 2018_Jul_Dec, as of 2026-09-29.

## Limitations

The weather the models saw is observed weather at the target hour, which a real day ahead
forecast does not have; every error figure is a lower bound on live error and every win against
the operator an upper bound for that reason, and the caveat is printed on every figure that uses
it. The operator's forecast is compared only where its scope matches the demand series;
7 authorities are excluded rather than counted. The
hierarchy is EIA's assignment of authorities to regions and interconnections, and the remainder
nodes are arithmetic devices rather than control areas. The detector's threshold was chosen on
the simulator because the real validation year has no labelled events; the real test year's
alerts are reported, not judged. The London panel is from 2011 to 2014, opted in, and the dynamic
tariff group was recruited, not randomized; the meter forecast uses a fixed panel of
4,485 households, hourly rather than half hourly because the
forecasting interface is hourly, and no weather. The live scorecard scores against the committed
actuals until the refresh job exists. The gbm backend trains on every
3 origin days to fit the day's compute. Single machine,
single region, free tiers throughout.
