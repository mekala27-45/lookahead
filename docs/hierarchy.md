# Hierarchy and reconciliation

The summing matrix is built from `data/hierarchy.csv`: the lower 48, the three interconnections,
13 regions, 51 authorities in the backtest,
83 eligible subregions and 8 remainder
nodes, one per authority with subregions, carrying the difference between the authority and its
published subregions so the leaves sum to the authority to the megawatt. The subregion series do
not exactly match their authority in the source (mean absolute gap
0.78%, worst 3.62% at
ISNE); nothing is scaled to fit.

Base forecasts come from the own backend at every series node, the aggregates forecast directly
as well as by aggregation. The remainder nodes are bookkeeping, near zero, and
1 of them negative through the validation year, so no model
is fit to them: each one's median is its authority's median minus its subregions', it carries no
interval of its own, and it is left out of the accuracy tables at the subregion level. Methods: bottom up; top down by the validation year's historical proportions;
MinT with the Schafer and Strimmer shrinkage of the base residual covariance on the validation
year (intensity 0.002). Quantile crossing after a linear
adjustment is removed at the leaves and the upper nodes rebuilt from them, so every reconciled set
is coherent and monotone in the level.

Coherence gaps: bottom up 0.0000 MW, top down
0.0000 MW, MinT 0.0000 MW;
the base forecasts disagree by up to 71,796 MW. Accuracy by level:

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

Helped at bottom_up at the lower 48 level; bottom_up at the interconnection level; bottom_up at the region level; mint at the lower 48 level; mint at the interconnection level; mint at the region level; hurt at top_down at the interconnection level; top_down at the region level; top_down at the authority level; top_down at the subregion level; mint at the authority level; mint at the subregion level. The method with
the lowest error summed over levels is bottom_up. On the simulator, against
the truth rather than the observed actuals, MinT's gain at the top on the base condition is
0.011 and at the leaves
-0.001.

Tests (`tests/hierarchy`): the summing matrix's rows match the hierarchy table; every method is
coherent to the megawatt; a base set that does not sum is the deliberate violation; an empty node
set is refused; a subregion set that does not sum to its authority is reported with its gap and
never silently scaled; the MinT covariance is estimated on validation only.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
