# Serving

The API (`packages/api`) is FastAPI over Postgres through SQLModel and Alembic. It loads the served
backend named in `results/registry/served.json` (gbm) from its export under
`results/models/` and the serving bundle of recent demand and weather per authority, and issues a
forecast at the latest origin the bundle allows: the last hour of demand that still has
48 hours of weather after it, snapped to the issue hour.

Routes: `POST /v1/forecasts` (issue and store; token), `GET /v1/forecasts/{id}` (with rows and
scores), `GET /v1/forecasts`, `POST /v1/score` (score every stored row whose target hour has an
actual; token), `GET /v1/scorecard`, `GET /v1/models`, `GET /v1/authorities`, `GET /v1/audit`,
`GET /v1/health`. Every response carries the statement. Every write goes: the rows, then the
audit row, then commit, then the response; `test_audit_precedes_response` holds it to that.

Deployed at https://lookahead-grid-api.fly.dev on Fly.io's free allowance (one shared CPU machine that
stops when idle and starts on the first request, which is why the site probes twice) with Neon
Postgres; the tables live in the `lookahead` schema when the database is shared with another
project. Verified from a separate client (AJAY, Windows, PowerShell 5.1.26100.9444) at 2026-09-30T22:21:51.1458679Z:
deployed, 48 rows read back, audit before
response yes. Latency from `scripts/load_test.py`:
2 measurement files (local p99 for issuing
42 ms); the registry's gate reads the latest.

Writes need the token and nothing else, because this is a demonstration. The refresh job that
would pull the latest EIA file and issue the day's forecasts is a stretch step; until it exists the
live scorecard scores against the committed actuals and the page says so.

> Demand data from the U.S. Energy Information Administration's Hourly Electric Grid Monitor, public domain; weather from Open-Meteo under CC BY 4.0; household data from UK Power Networks' Low Carbon London release under CC BY 4.0. Forecasts here are demonstrations and not for grid operations.
