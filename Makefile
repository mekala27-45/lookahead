# The pipeline in the order it runs. docs/runbook.md describes each target;
# tests/core/test_make_order.py fails if the Makefile's order disagrees with the stage order.

PY := uv run python
L := uv run lookahead

.PHONY: help setup data weather simulate recovery backtest hierarchy events meter registry manifest render marts pipeline gates lint types test check rederive web deploy verify-api load-test live-check demo clean

help:
	@grep -E '^[a-z-]+:' Makefile | sed 's/:.*//' | tr '\n' ' '; echo

setup:
	uv sync
	npm --prefix web ci

# The three public sources. Place the raw files under data/external if this machine cannot
# reach the hosts; the target prints the expected paths and verifies what it finds either way.
data:
	$(L) data

# Open-Meteo pulls per authority location, cached under data/external/weather and committed as parquet.
weather:
	$(L) weather

simulate:
	$(L) simulate

recovery:
	$(L) recovery

backtest:
	$(L) backtest --backend own
	$(L) backtest --backend gbm

hierarchy:
	$(L) hierarchy

events:
	$(L) events

meter:
	$(L) meter

registry:
	$(L) registry

manifest:
	$(L) manifest

render:
	$(PY) scripts/check_published_numbers.py --write

marts:
	$(L) marts

pipeline: simulate recovery backtest hierarchy events meter registry manifest render marts

gates:
	$(PY) scripts/check_no_em_dash.py
	$(PY) scripts/check_vocabulary.py
	$(PY) scripts/check_statement.py
	$(PY) scripts/check_published_numbers.py
	$(PY) scripts/scan_for_planted_identifiers.py
	node scripts/validate_palette.js --config web/src/theme/palette.json

lint:
	uv run ruff check .
	uv run ruff format --check .

types:
	uv run mypy

test:
	uv run pytest --cov --cov-report=term-missing:skip-covered

check: lint types gates test

rederive:
	$(PY) scripts/reset_and_rederive.py

web:
	npm --prefix web run build

# Deploys the API to Fly with the Neon connection string as a secret. Needs flyctl and the
# variables in .env; the sandbox that built this repository could not reach Fly, so the
# same steps live in deploy/deploy.ps1 for a Windows machine.
deploy:
	sh deploy/deploy.sh

verify-api:
	$(PY) scripts/check_persistence.py --base-url "$${LOOKAHEAD_API_BASE:-http://127.0.0.1:8080}"

load-test:
	$(PY) scripts/load_test.py --base-url "$${LOOKAHEAD_API_BASE:-http://127.0.0.1:8080}"

live-check:
	$(PY) scripts/live_check.py

demo:
	$(PY) scripts/build_demo_gif.py

clean:
	rm -rf results/scratch web/out logs/*.log
