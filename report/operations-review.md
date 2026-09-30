# Operations review: the forecast against the operator

Load desk, as of 2026-09-29. Rendered from `results/manifest.json`; every figure below is
a manifest value or table and `scripts/check_published_numbers.py` fails CI if this file drifts
from it.

## Skill against the operator

Over the test year (2025-09-29 to 2026-09-28), at
horizons 1 to 24, the served backend (gbm) beat the operator's published day ahead forecast in
18 of 44 comparable
balancing authorities (13 to
24 across bootstrap replicates of the test days), lost to it
in 17 (12 to
22) and tied in 9,
after Benjamini-Hochberg across the authorities. Pooled over the comparable hours its MAPE was
4.52% against the operator's
5.52%, a skill of +18.1%;
the median authority's skill was +3.2%. Over all 48 horizons
the MAPE was 5.48% (5.01% to
5.98%) against the seasonal naive's 11.66%.
At the daily peak the model's absolute error was 4.83%
against the operator's 103.78%, with a median timing
error of 1.0 h hours against
1.0 h.

7 authorities are not counted because the published
forecast covers a different scope than the demand series: FMPP (forecast to demand 1.01 validation, 0.76 test), FPC (forecast to demand 0.76 validation, 0.76 test), GVL (forecast to demand 0.91 validation, 0.89 test), PSCO (forecast to demand 0.94 validation, 0.83 test), PSEI (forecast to demand 0.72 validation, 0.53 test), SPA (forecast to demand 2.04 validation, 1.06 test), SWPP (forecast to demand 1.01 validation, 1.11 test).

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

The cross check: own has the lower error in 4 authorities and
gbm in 40; they fall on different sides of the operator in
8 of 44. Nothing is averaged.

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

## Coverage

The 90 percent bands covered 89.1% of the test year's hours
(88.6% to 89.6%) and
the 50 percent bands 49.0%. On the validation year the calibration
held 90.0% at the 90 percent level, inside the gate's
band of 85% to 95%. Shares of
actuals at or below each served level: 5.5%,
24.1%, 48.4%,
73.1% and 94.6% against
5, 25, 50, 75 and 95 percent; degenerate levels none.

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

## Where reconciliation helped and where it hurt

159 nodes from the lower 48 to the subregion, every one forecast directly
and reconciled by bottom up, top down and MinT (shrinkage intensity
0.002); every reconciled set is coherent to within
0.0000 MW where the base forecasts disagreed by up to
71,796 MW. Reconciliation helped at bottom_up at the lower 48 level; bottom_up at the interconnection level; bottom_up at the region level; mint at the lower 48 level; mint at the interconnection level; mint at the region level
and hurt at top_down at the interconnection level; top_down at the region level; top_down at the authority level; top_down at the subregion level; mint at the authority level; mint at the subregion level; the method with the lowest error summed over levels is
bottom_up. At the top MinT moved the MAPE from 2.65%
to 2.14%; at the leaves from 8.53% to
10.01%.

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

## The events the detector caught and missed

The detector watches the day's own forecast residual, standardized per authority, past
6.0 for 3 hours; hours a quarantine rule
flagged are data defects, never demand events. It detected 3 of the
10 rows of the known events table (30%) with a median
delay of 5.7 hours, and raised 0
alerts in the 4,924 window hours outside the events. Missed:
covid_2020 at NYIS, covid_2020 at MISO, ida_2021 at MISO.8910, ida_2021 at MISO, elliott_2022 at TVA, elliott_2022 at DUK, elliott_2022 at CPLE. Over the real test year it raised 277
alerts, 71 demand events and 206 data
defects. On the demonstration grid it recovered 6 of
6 planted defects as defects, 1 of
2 planted load sheds, with 8 false alarms.

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

## The meter

5,358 London households in 3 load shape clusters;
cluster 1 (evening peak) carries
50.5% of the weekday evening peak with
52.3% of the households. Under the pre-registered plan
(hash `b1c595ba7016`), the dynamic time of use group used
-5.8% (-7.0% to
-4.7%) during the 69 high price events
against matched standard households, -0.160 kWh per household per event,
with a rebound of +0.2% afterwards; 4 of
4 event types are distinguishable from zero after correction. The cluster
forecast, reconciled by MinT, moved the panel total's MAPE from 4.30%
to 4.26% and the clusters' from
6.78% to 9.12%. A program
buying peak reduction at 60 pounds per kilowatt would approach
cluster 0 first.

| Event type | Events | Response | lower | upper | p value | After correction |
|---|---:|---:|---:|---:|---:|---|
| night | 11 | -6.0% | -7.9% | -3.3% | 0.000 | different from zero |
| morning | 15 | -9.4% | -10.6% | -8.0% | 0.000 | different from zero |
| afternoon | 3 | -6.5% | -6.5% | -6.5% | 0.000 | different from zero |
| evening | 40 | -4.8% | -6.0% | -3.4% | 0.000 | different from zero |

Source: real:lcl, 1088 matched pairs over 69 high price events of 2013, 500 seeds, as of 2026-09-29.

| Cluster | Shape | Households | Evening kW per household | Share of the evening peak | Value of a 10 pct cut, GBP per household |
|---|---|---:|---:|---:|---:|
| 1 | evening peak | 2,802 | 0.58 | 50.5% | 3.5 |
| 0 | evening peak | 2,502 | 0.63 | 48.8% | 3.8 |
| 2 | night heavy | 54 | 0.47 | 0.8% | 2.8 |

Source: real:lcl, model gbm, 4485 households reporting through the whole forecast window, 352 origins, as of 2026-09-29.

## The live log and the registry

The API serves gbm, chosen by 7 gates
(gbm cleared every gate with the best headline (wins minus losses +1)). The separate client verification is deployed at
https://lookahead-grid-api.fly.dev: 48 rows read back, audit row before
the response yes, unscored share after scoring
0.0%. The live browser check not checked. Latency: local p99 for
issuing a forecast 42 ms.

## Limitations

The models saw observed weather at the target hour; a real day ahead forecast sees a weather
forecast, so every error figure here is a lower bound on what a live desk would see and every win
against the operator an upper bound. The operator's forecast is compared only where its scope
matches the demand series. The hierarchy is EIA's. The detector's threshold was chosen on the
simulator because the real validation year has no labelled events. The London panel is from 2011
to 2014, opted in, and the tariff group was not randomized; the meter forecast uses a fixed panel
of 4,485 households and no weather. The live scorecard scores against
the committed actuals until the refresh job exists.

## What the operator would push back on

You used observed weather, my forecast has a meteorologist behind it, your hierarchy is mine and
not yours, and your households are a decade old and volunteered. All four are true and each is
stated where it applies: the weather caveat on every figure that uses it, the comparability rule
that drops 7 authorities rather than counting them, the
remainder nodes that keep the arithmetic honest without pretending to be control areas, and the
pre-registered plan that stops the tariff estimate from being tuned. What the build did not do is
give the model a weather forecast, and it says so first.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
