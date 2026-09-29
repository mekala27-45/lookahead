# Decisions

Dated entries, newest last. Two of them are reversals and say so. Numbers here are the ones the
decision was made on; the current values are in `RESULTS.md`, rendered from the manifest.

## 2026-09-29: the data comes in through the PC, not the sandbox

The build environment could not reach eia.gov, open-meteo.com or data.london.gov.uk. Rather than
substitute a mirror or a sample, the fetch script (`deploy/fetch-data.ps1` in the data folder on the
PC) downloaded every six month file, every weather pull and the London release on the user's
machine, and the files were staged into the build in pieces. The sandbox also blocked EIA's future
half years, which EIA answers with an HTML page and a 200: the discovery step ignores any file under
a megabyte for that reason.

## 2026-09-29: NaN is a missing value, never the largest number

Polars orders NaN above every number in a comparison, so a quarantine rule written as
`demand > 3 x median` flags a NaN as a spike. Every rule now runs after `fill_nan(None)`, and the
quarantine tests hold a NaN fixture to that.

## 2026-09-29: subregions that do not sum get a remainder node, not a rescale

EIA's subregion series do not exactly match their authority's demand (the measured gap is in
`data/eia930/subregion_gap.parquet` and in `docs/hierarchy.md`). The hierarchy carries a `.rest`
node per authority with subregions holding the difference, so the leaves sum to the authority to the
megawatt without any series being scaled to fit. Top down by historical proportions splits into
remainder nodes too, which is one reason it hurts at the leaves.

## 2026-09-29: weather columns are scaled to the target's units, and temperature enters as a change

The first own model put raw degree hours beside a ratio target and its threshold search was
indifferent to the threshold. Degree hours are now scaled by the authority's typical demand over
its scale, and the raw temperature column was replaced by the change in heating and cooling degree
hours against the same hour lag. On the clean simulator the thresholds are then recovered exactly;
the own MAPE on the simulator fell from about 4 percent to under 2.

## 2026-09-29: reversal, XGBoost replaces LightGBM for the gbm backend

The brief names LightGBM. Its quantile objective renews the leaf values after every round, and on
the pooled design (about 900 thousand rows after thinning) that cost about 1.2 seconds a round even
on a one in seven sample, which put thirteen monthly refits at five levels near six hours. XGBoost's
`reg:quantileerror` fits all five levels in one booster with a vector `quantile_alpha` at about
half a second a round on the full thinned design, so the day's compute fit. The interface, the
features, the conformalization and the tests did not change; the card and the README say XGBoost.

## 2026-09-29: the operator comparison has a comparability rule

Some published day ahead forecasts cover a different footprint than the demand series (one
authority's forecast is negative, another's runs at about half its demand). A forecast that is not
comparable would count as a free win. An authority is comparable only when the median forecast to
demand ratio sits within 0.9 to 1.1 in both the validation and the test year; the rest are listed
with the reason and never counted. A quarantine rule, `forecast_nonpositive`, nulls a published
forecast at or below zero and counts it.

## 2026-09-29: the API shares one Neon database in its own schema

The free Neon allowance is one project. The marginal build's API already lives in it. Rather than
create a second project or collide on `audit_log`, the deploy uses `DATABASE_URL` with
`LOOKAHEAD_DB_SCHEMA=lookahead`: Alembic creates the schema and the API's engines qualify every
table name with it (see the entry below on why the search path was not enough), so the two
projects never touch each other's tables. `LOOKAHEAD_DATABASE_URL`, when set, gives the API a
database of its own instead.

## 2026-09-29: reversal, the palette moved five slots

The brief's dark categorical slots two, five and seven and the dark diverging midpoint failed the
ported validator (adjacent color vision deficiency separation and contrast on the dark card), and
the light categorical slot six failed the light card. Each was moved by the smallest change that
passes: dark slot two from #B98A14 to #C7982B, slot five from #9C7BE0 to #906ED2, slot seven from
#5B8DEF to #5182E3, the dark midpoint from #232E40 to #292E35, and light slot six from #B4561E to
#B75921. `scripts/validate_palette.js` runs in CI against exactly the committed values, including
the dark card run.

## 2026-09-29: reconciled quantiles are sorted at the leaves, not at every node

Sorting every node's levels after MinT removed crossing but broke coherence by up to 13 MW where
a node's crossing differed from its leaves'. The reconciled leaves are sorted across levels and the
upper nodes rebuilt from them: a sum of ascending sequences is ascending, so the result is coherent
and monotone. A test holds the method to it.

## 2026-09-29: the simulator plants events in the validation year as well as the test year

The detector's threshold has to be chosen on a validation year with known events, so the simulator
plants one event of each kind per authority in the validation year too, at different calendar
positions from the test year's. The real validation year has no labelled events; the threshold is
chosen on the demonstration grid and carried to the real grid by the standardized scale.

## 2026-09-29: the detector watches the own backend's residuals whichever backend is served

own refits at every origin and its conformal calibration on the validation year gives the robust
residual scale per authority for free; gbm's calibration does not export residual quantiles. The
events page says which forecast the residuals belong to.

## 2026-09-29: the meter forecast is hourly, on a fixed panel

The forecasting interface is hourly, so the cluster loads are summed to hours before the gbm
backend sees them; the clusters and the time of use analysis stay half hourly. The panel is fixed
to the households that report through the whole forecast window, because a series summed over a
panel that is still recruiting measures recruitment, not consumption. Both are stated in the
README's first paragraph as the subsamples they are.

## 2026-09-29: the time of use analysis was pre-registered before the readings were examined

`docs/tou_plan.md` names the population, the matching, the events, the outcome, the estimator, the
bootstrap and the correction; its SHA-256 is recorded by the meter stage and rendered in the report,
and a test holds the recorded hash to the committed file.

## 2026-09-29: the fonts are served from Fontsource packages, not Google Fonts

The brief asks for self hosting through `next/font`. The build environment cannot reach Google
Fonts, and the Fontsource variable packages for Space Grotesk, Atkinson Hyperlegible Next and
Atkinson Hyperlegible Mono ship the same woff2 files, which Next bundles from `node_modules` at
build time. The site fetches nothing from any host but its own.

## 2026-09-29: the backtest's prediction frames stay out of git

Each backend's prediction and scoring frames run to tens of megabytes; three backends and a
rederive would have doubled the repository. The summaries, the manifests, the model exports, the
serving bundle and the marts are committed; `make backtest` rebuilds the frames.

## 2026-09-29: the schema goes in the SQL, not in the connection's search path

The first deploy set `search_path` through the `options` startup parameter on every connection.
Locally that works; the hosted database's proxy dropped the parameter, so Alembic created the
tables in the schema (its migration sets the search path with a statement) and the API, searching
`public`, answered that `forecasts` did not exist. The health check said only "unreachable" and
logged nothing, which is now also fixed. The engines use SQLAlchemy's `schema_translate_map`
instead, so every emitted table name carries the schema whatever the connection's search path
says, and the test resets the search path to `public` before reading the rows back. The second
deploy then found no tables at all: both projects' first migration is revision `0001`, and
alembic, looking up its version table through the search path, had read the other project's
`public.alembic_version` and concluded there was nothing to do. The version table is now named
with the schema, and a test plants a decoy version table in `public` before migrating.

## 2026-09-29: remainder nodes are derived, not forecast, and not scored

On the real grid two remainder nodes are near zero and one is negative through the whole
validation year (the published subregions of that authority sum to more than its demand), so the
ratio model's calibration had no usable row and the first hierarchy run stopped. A remainder is
bookkeeping: its median is now the parent's median minus the siblings', its actuals and its
validation residuals likewise, it carries no interval of its own, and it is left out of the
accuracy tables at the subregion level. Bottom up therefore reproduces each such authority's own
median exactly, which a test holds.

